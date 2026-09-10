#!/usr/bin/env python3
"""Readiness gate, exactly one Nav2 goal, and honest runtime evidence for Video 1."""
import argparse
from collections import defaultdict, deque
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.logging import LoggingSeverity
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
from rclpy.time import Time
from action_msgs.msg import GoalStatus, GoalStatusArray
from dwb_msgs.msg import LocalPlanEvaluation
from gazebo_msgs.srv import GetEntityState
from lifecycle_msgs.srv import GetState
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry, Path as NavPath
from rcl_interfaces.msg import Log
from rcl_interfaces.srv import GetParameters
from sensor_msgs.msg import LaserScan
from social_nav_msgs.msg import Pedestrians
from tf2_ros import Buffer, TransformListener, TransformException
import yaml
from ament_index_python.packages import get_package_share_directory
from demo_math import stamp_seconds, speed_stats, transform, wrap, yaw

LIFECYCLES = ('amcl', 'map_server', 'controller_server', 'planner_server',
              'smoother_server', 'behavior_server', 'bt_navigator',
              'waypoint_follower', 'velocity_smoother')


def parameter_value(p):
    return {1: p.bool_value, 2: p.integer_value, 3: p.double_value,
            4: p.string_value, 9: list(p.string_array_value)}.get(p.type)


class Recorder(Node):
    def __init__(self, args):
        super().__init__('video1_recording_control',
                         parameter_overrides=[Parameter('use_sim_time', value=True)])
        if not self.get_parameter('use_sim_time').value:
            raise RuntimeError('Recorder requires use_sim_time:=true')
        self.args = args
        self.out = Path(args.output)
        self.out.mkdir(parents=True, exist_ok=True)
        self.events = (self.out / 'observations.jsonl').open('w', buffering=1)
        params = Path(get_package_share_directory('museum_assistant')) / 'config/nav2_supplied_anisotropic.yaml'
        accepted = yaml.safe_load(params.read_text())['controller_server']['ros__parameters']['FollowPath']
        # Guard every accepted social parameter, plugin class, and critic list.
        self.expected = {'FollowPath.'+k: v for k, v in accepted.items()
                         if k.startswith('ProxemicForce.') or k in ('plugin', 'critics')}
        self.diagnostics = {}
        self.fatal_error = None
        self.ready_reached = False
        self.dds_probe = {'status': 'NOT_RUN'}
        self.runtime_log_offset = 0
        self.state_times = {}
        self.pending_times = {}
        self.last_sim = 0.0
        self.last_clock_wall = time.monotonic()
        self.robot_frame = None
        self.actual = None
        self.states, self.pending = {}, {}
        self.lifecycle_clients = {name: self.create_client(GetState, f'/{name}/get_state') for name in LIFECYCLES}
        self.param_client = self.create_client(GetParameters, '/controller_server/get_parameters')
        self.actor_client = self.create_client(GetEntityState, '/gazebo/get_entity_state')
        self.action = ActionClient(self, NavigateToPose, '/navigate_to_pose')
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.people, self.raw = deque(maxlen=300), deque(maxlen=300)
        self.speeds = defaultdict(list)
        self.people_stamps = []
        self.people_wall_stamps = []
        self.robot = None
        self.robot_time = None
        self.min_distance = None
        self.pose_errors = []
        self.observed_actor = []
        self.goal_ids = set()
        self.goal_count = 0
        self.recoveries = 0
        self.no_trajectories = 0
        self.no_progress = 0
        self.critic_samples = 0
        self.critic_nonzero = 0
        self.critic_varied = 0
        self.laser_observations = 0
        self.laser_associations = 0
        self.costmap_observations = 0
        self.costmap_associations = 0
        self.paths = defaultdict(int)
        self.last_angular_sign = 0
        self.sign_candidate = None
        self.reversals = 0
        self.stationary_spin = 0.0
        self.max_stationary_spin = 0.0
        self.rotation = 0.0
        self.path_x = []
        self.goal_handle = None
        self.raw_robot = None
        self.started_wall = time.monotonic()
        self.first_sim = None
        self.last_poll = 0.0
        self.last_render = 0.0
        # Best-effort readers match both reliable and sensor-data publishers.
        # Critical streams still have explicit freshness/readiness gates.
        for kind, topic, callback, critical in (
            (Pedestrians, '/people', self.on_people, True),
            (Pedestrians, '/museum/video1/actor_states', self.on_actor_state, True),
            (Odometry, '/museum/ground_truth_odom', self.on_odom, True),
            (Odometry, '/ground_truth_odom', self.on_raw_robot, False),
            (LaserScan, '/scan_raw', self.on_scan, False),
            (OccupancyGrid, '/local_costmap/costmap', self.on_costmap, False),
            (LocalPlanEvaluation, '/evaluation', self.on_evaluation, False),
            (Log, '/rosout', self.on_log, False),
        ):
            self.diagnostics[topic] = {'status': 'WAITING_FOR_MESSAGE', 'samples': 0, 'errors': 0}
            self.create_subscription(kind, topic, self.guard(topic, callback, critical),
                                     qos_profile_sensor_data)
        self.create_subscription(GoalStatusArray, '/navigate_to_pose/_action/status',
                                 self.guard('action_status', self.on_status, True),
                                 QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        for topic in ('/plan', '/local_plan'):
            self.diagnostics[topic] = {'status': 'WAITING_FOR_MESSAGE', 'samples': 0, 'errors': 0}
            self.create_subscription(NavPath, topic,
                                     self.guard(topic, lambda m, t=topic: self.on_path(t, m)),
                                     qos_profile_sensor_data)

    def diagnostic_error(self, name, exc):
        entry = self.diagnostics.setdefault(name, {'samples': 0, 'errors': 0})
        entry.update(status='ERROR', last_error=f'{type(exc).__name__}: {exc}')
        entry['errors'] += 1
        if entry['errors'] == 1:
            print(f'Diagnostic {name}: {entry["last_error"]}', flush=True)
        self.event('diagnostic_error', source=name, error=entry['last_error'])

    def guard(self, name, callback, critical=False):
        def guarded(message):
            try:
                callback(message)
                entry = self.diagnostics.setdefault(name, {'samples': 0, 'errors': 0})
                entry['samples'] += 1
                entry['status'] = 'OBSERVED_WITH_ERRORS' if entry['errors'] else 'OBSERVED'
            except Exception as exc:
                self.diagnostic_error(name, exc)
                if critical:
                    self.fatal_error = f'Critical input {name}: {exc}'
        return guarded

    def on_actor_state(self, msg):
        self.validate_people(msg)
        self.raw.append(msg)

    def validate_people(self, msg):
        if not msg.header.frame_id or not math.isfinite(stamp_seconds(msg.header.stamp)):
            raise ValueError('Missing frame or invalid timestamp')
        for p in msg.pedestrians:
            if not all(math.isfinite(v) for v in
                       (p.pose.x, p.pose.y, p.pose.theta, p.velocity.x, p.velocity.y)):
                raise ValueError('Nonfinite people sample')

    def on_feedback(self, msg):
        self.recoveries = max(self.recoveries, int(msg.feedback.number_of_recoveries))

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def on_raw_robot(self, msg):
        p = msg.pose.pose
        pose = (p.position.x, p.position.y, yaw(p.orientation))
        if not all(math.isfinite(v) for v in pose):
            raise ValueError('Nonfinite world odometry')
        self.raw_robot = pose

    def event(self, kind, **data):
        try:
            self.events.write(json.dumps({'kind': kind, **data}, allow_nan=False)+'\n')
        except (OSError, ValueError, TypeError) as exc:
            self.fatal_error = f'Cannot record evidence: {exc}'

    def on_status(self, msg):
        self.goal_ids.update(bytes(s.goal_info.goal_id.uuid).hex() for s in msg.status_list)

    def on_path(self, topic, msg):
        if msg.poses:
            self.paths[topic] += 1

    def on_log(self, msg):
        if re.search('No valid trajectories', msg.msg, re.I):
            self.no_trajectories += 1
        if re.search('Failed to make progress', msg.msg, re.I):
            self.no_progress += 1
        # Log's IDL byte constants can be bytes on Humble; rcutils severity
        # is a numeric enum. Accept either generated representation of level.
        level = msg.level
        if isinstance(level, (bytes, bytearray)) and len(level) == 1:
            level = level[0]
        if not isinstance(level, int):
            raise TypeError(f'Unexpected log severity {level!r}')
        if level >= int(LoggingSeverity.WARN):
            self.event('ros_log', t=stamp_seconds(msg.stamp), node=msg.name, level=level, text=msg.msg)

    def on_people(self, msg):
        self.validate_people(msg)
        if self.now() <= 0:
            return
        t = stamp_seconds(msg.header.stamp)
        self.people.append(msg)
        self.people_stamps.append(t)
        self.people_wall_stamps.append(time.monotonic())
        rows = []
        for p in msg.pedestrians:
            values = [p.pose.x, p.pose.y, p.pose.theta, p.velocity.x, p.velocity.y]
            if not all(math.isfinite(v) for v in values):
                raise RuntimeError('Nonfinite /people sample')
            self.speeds[p.identifier].append((t, p.velocity.x, p.velocity.y))
            rows.append([p.identifier, *values])
        self.event('people', t=t, frame=msg.header.frame_id, rows=rows)

    def lookup(self, target, source, t):
        if target == source:
            return (0.0, 0.0, 0.0)
        try:
            tf = self.tf.lookup_transform(target, source, Time(seconds=t)).transform
            return (tf.translation.x, tf.translation.y, yaw(tf.rotation))
        except TransformException:
            return None

    def nearby_people(self, t, frame):
        if not self.people:
            return []
        msg = min(self.people, key=lambda m: abs(stamp_seconds(m.header.stamp)-t))
        dt = t - stamp_seconds(msg.header.stamp)
        # Static fallback is sampled at 1 Hz; actor observations at 20 Hz.
        if abs(dt) > (1.1 if self.args.mode == 'static' else 0.15):
            return []
        tf = self.lookup(frame, msg.header.frame_id, t)
        if tf is None:
            return []
        return [(p.identifier, *transform(p.pose.x+p.velocity.x*dt, p.pose.y+p.velocity.y*dt, tf))
                for p in msg.pedestrians if p.identifier != 'visitor_1']

    def on_odom(self, msg):
        t = stamp_seconds(msg.header.stamp)
        if self.now() <= 0 or t <= 0:
            return
        if self.robot_time is not None and t < self.robot_time:
            raise RuntimeError('Odometry timestamp moved backwards')
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        if not msg.header.frame_id or not all(math.isfinite(v) for v in
                (p.x, p.y, q.x, q.y, q.z, q.w, msg.twist.twist.linear.x,
                 msg.twist.twist.linear.y, msg.twist.twist.angular.z)):
            raise ValueError('Invalid odometry')
        self.robot_frame = msg.header.frame_id
        if self.robot_time is not None and t-self.robot_time < 0.09:
            return
        dt = 0.0 if self.robot_time is None else min(t-self.robot_time, 0.5)
        if dt < 0:
            raise RuntimeError('Simulation clock reset; restart this experiment')
        self.robot_time = t
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        self.robot = (p.x, p.y, yaw(q))
        self.path_x.append(p.x)
        v = math.hypot(msg.twist.twist.linear.x, msg.twist.twist.linear.y)
        w = msg.twist.twist.angular.z
        self.rotation += abs(w)*dt
        spinning = v < 0.025 and abs(w) > 0.08
        self.stationary_spin = self.stationary_spin + dt if spinning else 0.0
        self.max_stationary_spin = max(self.max_stationary_spin, self.stationary_spin)
        sign = 1 if w > 0.08 else -1 if w < -0.08 else 0
        if sign and sign != self.last_angular_sign:
            if self.sign_candidate is None or self.sign_candidate[0] != sign:
                self.sign_candidate = (sign, t)
            elif t-self.sign_candidate[1] >= 0.5:
                self.reversals += int(self.last_angular_sign != 0)
                self.last_angular_sign = sign
                self.sign_candidate = None
        else:
            self.sign_candidate = None
        try:
            for _, x, y in self.nearby_people(t, msg.header.frame_id):
                d = math.hypot(x-p.x, y-p.y)
                self.min_distance = d if self.min_distance is None else min(self.min_distance, d)
        except Exception as exc:
            self.diagnostic_error('person_separation', exc)
        self.event('robot', t=t, frame=msg.header.frame_id, x=p.x, y=p.y,
                   yaw=self.robot[2], speed=v, angular_speed=w)

    def on_scan(self, msg):
        t = stamp_seconds(msg.header.stamp)
        people = self.nearby_people(t, msg.header.frame_id)
        if not people:
            return
        candidates = [(n, x, y) for n, x, y in people if math.hypot(x, y) < min(msg.range_max, 6.0)]
        hits = set()
        for i, r in enumerate(msg.ranges):
            if not math.isfinite(r) or not msg.range_min <= r <= msg.range_max:
                continue
            a = msg.angle_min+i*msg.angle_increment
            x, y = r*math.cos(a), r*math.sin(a)
            hits.update(n for n, px, py in candidates if math.hypot(px-x, py-y) < 0.40)
        self.laser_observations += int(bool(candidates))
        self.laser_associations += int(bool(hits))
        self.event('scan_association', t=t, candidates=[p[0] for p in candidates], near_actor_endpoints=sorted(hits))

    def on_costmap(self, msg):
        t = stamp_seconds(msg.header.stamp)
        origin = msg.info.origin
        if (not math.isfinite(msg.info.resolution) or msg.info.resolution <= 0
                or len(msg.data) != msg.info.width*msg.info.height):
            raise ValueError('Empty or malformed costmap geometry')
        if abs(yaw(origin.orientation)) > 1e-6:
            raise ValueError('Rotated costmap origin is unsupported')
        n = 0
        hits = []
        for name, x, y in self.nearby_people(t, msg.header.frame_id):
            ix = int(math.floor((x-origin.position.x)/msg.info.resolution))
            iy = int(math.floor((y-origin.position.y)/msg.info.resolution))
            if not (0 <= ix < msg.info.width and 0 <= iy < msg.info.height):
                continue
            n += 1
            radius = math.ceil(0.40/msg.info.resolution)
            cells = [msg.data[b*msg.info.width+a]
                     for a in range(max(0, ix-radius), min(msg.info.width, ix+radius+1))
                     for b in range(max(0, iy-radius), min(msg.info.height, iy+radius+1))
                     if (a-ix)**2+(b-iy)**2 <= radius**2]
            if any(c == 100 for c in cells):
                hits.append(name)
        self.costmap_observations += int(n > 0)
        self.costmap_associations += int(bool(hits))
        self.event('costmap_association', t=t, in_window=n, lethal_near_people=hits)

    def on_evaluation(self, msg):
        raw = [s.raw_score for tr in msg.twists for s in tr.scores if s.name == 'ProxemicForce']
        raw = [v for v in raw if math.isfinite(v)]
        if raw:
            self.critic_samples += 1
            self.critic_nonzero += int(max(raw) > 0.01)
            self.critic_varied += int(max(raw)-min(raw) > 1e-5)

    def request(self, key, client, request, callback):
        if key in self.pending or not client.service_is_ready():
            return
        try:
            future = client.call_async(request)
        except Exception as exc:
            self.diagnostic_error(key, exc)
            return
        self.pending[key] = future
        self.pending_times[key] = time.monotonic()
        def done(f):
            if self.pending.get(key) is not f:
                return
            self.pending.pop(key, None)
            self.pending_times.pop(key, None)
            self.guard(key, lambda value: callback(value.result()))(f)
        future.add_done_callback(done)

    def poll(self):
        wall = time.monotonic()
        if wall-self.last_poll < 1.0:
            return
        self.last_poll = wall
        runtime_log = self.out/'runtime.log'
        if runtime_log.exists():
            try:
                with runtime_log.open(errors='replace') as log:
                    log.seek(self.runtime_log_offset)
                    recent = log.read()
                    self.runtime_log_offset = log.tell()
            except OSError as exc:
                self.diagnostic_error('runtime_log', exc)
            else:
                if 'Failed to find a free participant index' in recent:
                    self.dds_probe = {'status': 'FAIL', 'error': 'DDS participant exhaustion in runtime.log'}
                    raise RuntimeError('DDS participant exhaustion during startup; see runtime.log; experiment invalid')
        for key, sent in list(self.pending_times.items()):
            if wall-sent > 5.0:
                future = self.pending.pop(key)
                self.pending_times.pop(key)
                future.cancel()
                self.diagnostic_error(key, TimeoutError('Service response exceeded 5 wall seconds'))
        for name, client in self.lifecycle_clients.items():
            def state_done(response, n=name):
                self.states[n] = int(response.current_state.id)
                self.state_times[n] = time.monotonic()
            self.request(name, client, GetState.Request(), state_done)
        if self.actual is None:
            def params_done(response):
                if len(response.values) != len(self.expected):
                    raise ValueError('Incomplete parameter response')
                values = dict(zip(self.expected, map(parameter_value, response.values)))
                if any(v is None for v in values.values()):
                    raise ValueError('Required critic parameter is unset or unsupported')
                self.actual = values
            self.request('params', self.param_client,
                         GetParameters.Request(names=list(self.expected)), params_done)
        if self.args.mode == 'actor' and self.now() > 0 and self.raw:
            self.request('actor', self.actor_client,
                         GetEntityState.Request(name='video1_walker_1', reference_frame='world'),
                         self.actor_observation)

    def actor_observation(self, response):
        if not response.success:
            raise ValueError('Gazebo GetEntityState did not find video1_walker_1')
        if not self.raw:
            return
        t = stamp_seconds(response.header.stamp)
        raw = min(self.raw, key=lambda m: abs(stamp_seconds(m.header.stamp)-t))
        dt = t-stamp_seconds(raw.header.stamp)
        if abs(dt) > 0.15 or len(raw.pedestrians) != 1:
            return
        p = raw.pedestrians[0]
        actual = response.state.pose.position
        error = math.hypot(actual.x-p.pose.x-p.velocity.x*dt, actual.y-p.pose.y-p.velocity.y*dt)
        if not all(math.isfinite(v) for v in (t, actual.x, actual.y, error)):
            raise ValueError('Nonfinite Gazebo actor observation')
        self.pose_errors.append(error)
        self.observed_actor.append((t, actual.x, actual.y))
        self.event('actor_observation', t=t, world_x=actual.x, world_y=actual.y, extrapolated_pose_error=error)

    def nav_active(self):
        return all(self.states.get(n) == 3 and
                   time.monotonic()-self.state_times.get(n, 0) < 5.0 for n in LIFECYCLES)

    def ready(self):
        if self.fatal_error:
            raise RuntimeError(self.fatal_error)
        if self.now() <= 0 or not self.nav_active():
            return False
        if self.actual is None:
            return False
        if self.actual != self.expected:
            raise RuntimeError('Runtime critic parameters differ from the accepted YAML')
        if self.robot_time is None or not -0.1 <= self.now()-self.robot_time <= 0.5:
            return False
        if not self.action.server_is_ready():
            return False
        if self.args.mode == 'baseline':
            return not self.people or not self.people[-1].pedestrians
        expected = 10 if self.args.mode == 'static' else 1
        if not self.people or len(self.people[-1].pedestrians) != expected or self.count_publishers('/people') != 1:
            return False
        age = self.now()-stamp_seconds(self.people[-1].header.stamp)
        if not -0.1 <= age < (1.1 if self.args.mode == 'static' else 0.3):
            return False
        if self.args.mode == 'actor':
            samples = self.speeds.get('walker_1', [])
            recent = [s for s in samples if s[0] >= self.now()-3.0]
            if len(recent) < 30 or recent[-1][0]-recent[0][0] < 2.0:
                return False
            if any(math.hypot(vx, vy) <= 0.10 for _, vx, vy in recent):
                raise RuntimeError('Moving actor does not sustain the anisotropy threshold')
            if (not self.pose_errors or max(self.pose_errors) > 0.05
                    or not 0 <= self.now()-self.observed_actor[-1][0] < 3.0):
                return False
        return True

    def step(self):
        rclpy.spin_once(self, timeout_sec=0.05)
        if self.fatal_error:
            raise RuntimeError(self.fatal_error)
        sim = self.now()
        if sim < self.last_sim:
            raise RuntimeError('Simulation clock reset; restart this experiment')
        if sim > self.last_sim:
            self.last_clock_wall = time.monotonic()
        if self.first_sim is not None and time.monotonic()-self.last_clock_wall > 60:
            raise RuntimeError('Simulation clock stalled for 60 wall seconds')
        self.last_sim = sim
        if self.first_sim is None and sim > 0:
            self.first_sim = (self.now(), time.monotonic())
        self.poll()
        if len(self.goal_ids) > 1:
            raise RuntimeError('More than one navigation goal observed')
        if self.goal_count and not self.nav_active():
            raise RuntimeError('Nav2 lifecycle readiness lost during navigation')
        if self.goal_count and self.args.mode == 'actor':
            if not self.people or self.now()-stamp_seconds(self.people[-1].header.stamp) > 0.8:
                raise RuntimeError('Actor /people stream lost during navigation')
        if time.monotonic()-self.last_render >= 1:
            self.last_render = time.monotonic()
            moving = [] if not self.people else [p for p in self.people[-1].pedestrians
                       if p.identifier != 'visitor_1' and math.hypot(p.velocity.x, p.velocity.y) > 0.10]
            speed = max((math.hypot(p.velocity.x, p.velocity.y) for p in moving), default=0.0)
            nav = 'ACTIVE' if self.nav_active() else 'WAITING'
            print(f'Nav2: {nav} | Animated people: {int(self.args.mode == "actor")} '
                  f'| Moving people: {len(moving)} | moving speed: {speed:.3f} m/s '
                  f'| sim: {self.now():.1f}s | goal count: {self.goal_count} '
                  f'| actor pose samples: {len(self.pose_errors)} | diagnostics: '
                  f'{sum(d["errors"] for d in self.diagnostics.values())}', flush=True)
            if not self.goal_count:
                waiting = [n for n in LIFECYCLES if self.states.get(n) != 3
                           or time.monotonic()-self.state_times.get(n, 0) >= 5.0]
                print(f'Readiness: lifecycle waiting={waiting}; parameters={self.actual is not None}; '
                      f'odom={self.robot_time}; people messages={len(self.people_stamps)}; '
                      f'action server={self.action.server_is_ready()}', flush=True)

    def wait_future(self, future, wall_timeout=20.0):
        deadline = time.monotonic()+wall_timeout
        while not future.done() and time.monotonic() < deadline:
            self.step()
        if not future.done():
            raise RuntimeError('ROS operation timed out')
        try:
            result = future.result()
        except Exception as exc:
            raise RuntimeError(f'ROS action operation failed: {exc}') from exc
        if result is None:
            raise RuntimeError('ROS action returned no result')
        return result

    def check_dds_admission(self):
        output = self.out/'dds_probe.json'
        command = [sys.executable, str(Path(__file__).with_name('probe_dds.py')),
                   '--mode', self.args.mode, '--output', str(output), '--timeout', '20']
        self.dds_probe = {'status': 'RUNNING'}
        print('Stack ready: testing a NEW DDS participant and /clock, /map, /people, controller_manager...', flush=True)
        with (self.out/'dds_probe.log').open('w') as log:
            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic()+25
                while child.poll() is None:
                    self.step()  # keep lifecycle polling, /people and diagnostics alive
                    if time.monotonic() > deadline:
                        raise RuntimeError('DDS admission probe process timed out')
                if output.exists():
                    self.dds_probe = json.loads(output.read_text())
                if child.returncode != 0 or self.dds_probe.get('status') != 'PASS':
                    raise RuntimeError('Fresh DDS participant check failed; see dds_probe.log and dds_probe.json; no goal sent')
            except Exception as exc:
                self.dds_probe.update(status='FAIL', error=str(exc))
                raise
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
        self.event('dds_admission', **self.dds_probe)

    def run(self):
        print('ONE-ACTOR PROOF OF CONCEPT — visual walking and final crowd are NOT yet accepted.', flush=True)
        print('ProxemicForce: scale=32.0 comfort_distance=1.0 sigma=0.4 anisotropic_enabled=true (runtime checked)', flush=True)
        print('Goal: north_gallery (0,16,1.5708), exactly once after readiness. No robot waypoints.', flush=True)
        deadline = time.monotonic()+600.0
        while not self.ready():
            self.step()
            if time.monotonic() > deadline:
                raise RuntimeError('Readiness timeout; see runtime.log and observations.jsonl; no goal sent')
        self.check_dds_admission()
        if not self.ready():
            raise RuntimeError('Stack readiness lost during DDS admission check; no goal sent')
        self.ready_reached = True
        self.event('ready', t=self.now(), actual_parameters=self.actual)
        if self.args.observe_only:
            start = self.now()
            while self.now()-start < 60 and time.monotonic() < deadline:
                self.step()
            return 'OBSERVATION_ONLY'
        # Deterministic encounter schedule in simulation time. A late startup
        # must be rerun with a documented goal-time; never silently alter phase.
        if self.now() > self.args.goal_time-3.0:
            raise RuntimeError('Startup missed the fixed goal time; select a later --goal-time and rerun')
        while self.now() < self.args.goal_time:
            self.step()
            if time.monotonic() > deadline:
                raise RuntimeError('Simulation clock stalled before goal')
        if not self.ready():
            raise RuntimeError('Readiness lost at scheduled goal time; no goal sent')
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.y = 16.0
        goal.pose.pose.orientation.z = math.sin(1.5708/2)
        goal.pose.pose.orientation.w = math.cos(1.5708/2)
        self.goal_count += 1  # There is exactly one send_goal_async call.
        self.event('goal_sent', t=self.now(), x=0.0, y=16.0, yaw=1.5708)
        self.goal_handle = self.wait_future(self.action.send_goal_async(
            goal, feedback_callback=self.guard('action_feedback', self.on_feedback)))
        if not self.goal_handle.accepted:
            return 'REJECTED'
        future = self.goal_handle.get_result_async()
        result = self.wait_future(future, wall_timeout=1200.0)
        return 'SUCCESS' if result.status == GoalStatus.STATUS_SUCCEEDED else f'NAV2_STATUS_{result.status}'

    def finish(self, status, error):
        if self.goal_handle is not None and self.goal_handle.accepted and status != 'SUCCESS':
            try:
                future = self.goal_handle.cancel_goal_async()
                rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)
                if not future.done():
                    raise TimeoutError('Goal cancellation not acknowledged')
                response = future.result()
                self.event('goal_cancel_response', goals_canceling=len(response.goals_canceling))
            except Exception as exc:
                self.diagnostic_error('action_cancel', exc)
        sim = self.now()
        rtf = None if self.first_sim is None else (sim-self.first_sim[0])/(time.monotonic()-self.first_sim[1])
        final_map = None
        if self.robot is not None:
            tf = self.lookup('map', self.robot_frame, self.robot_time)
            if tf is not None:
                final_map = (*transform(self.robot[0], self.robot[1], tf), wrap(self.robot[2]+tf[2]))
        speeds = {k: speed_stats(v) for k, v in self.speeds.items()}
        observed_velocities = [((a[0]+b[0])/2, (b[1]-a[1])/(b[0]-a[0]), (b[2]-a[2])/(b[0]-a[0]))
                               for a, b in zip(self.observed_actor, self.observed_actor[1:]) if b[0] > a[0]]
        checks = {
            'fresh_dds_participant_after_readiness': self.dds_probe.get('status') == 'PASS',
            'navigation_success': status == 'SUCCESS',
            'exactly_one_goal': self.goal_count == 1 and len(self.goal_ids) == 1,
            'accepted_parameters': self.actual == self.expected,
            'map_goal_position': final_map is not None and math.hypot(final_map[0], final_map[1]-16.0) <= 0.5,
            'physical_goal_position': self.raw_robot is not None and math.hypot(self.raw_robot[0], self.raw_robot[1]-16.0) <= 0.5,
            'no_recovery': self.recoveries == 0,
            'no_invalid_trajectory_messages': self.no_trajectories == 0,
            'no_progress_failure_messages': self.no_progress == 0,
            'no_long_stationary_spin': self.max_stationary_spin <= 8.0,
            'limited_angular_reversals': self.reversals <= 6,
            'global_and_local_paths_observed': self.paths['/plan'] > 0 and self.paths['/local_plan'] > 0,
        }
        if self.args.mode != 'baseline':
            checks['human_disc_separation'] = self.min_distance is not None and self.min_distance > 0.63
            checks['critic_observed_scoring'] = self.critic_nonzero > 0 and self.critic_varied > 0
        if self.args.mode == 'actor':
            s = speeds.get('walker_1') or {}
            checks.update({
                'actor_pose_observed': len(self.pose_errors) >= 10 and max(self.pose_errors) <= 0.05,
                'heading_speed_sustained': s.get('above_0_10_percent', 0) >= 95 and s.get('zero_samples', 1) == 0,
                'no_velocity_spikes': (s.get('max_mps') or 999) < 0.5 and s.get('max_acceleration_mps2') is not None and s['max_acceleration_mps2'] < 0.5,
                'people_fresh_and_frequent': (s.get('sim_hz') or 0) >= 10 and (s.get('max_gap_sim_s') or 999) < 0.3,
                'laser_association_observed': self.laser_associations > 0,
                'costmap_association_observed': self.costmap_associations > 0,
            })
        # Missing optional evidence is inconclusive, never a measured failure.
        if not self.goal_count:
            checks = {name: None for name in checks}
        else:
            for name, observed in (
                ('critic_observed_scoring', self.critic_samples),
                ('laser_association_observed', self.laser_observations),
                ('costmap_association_observed', self.costmap_observations),
                ('global_and_local_paths_observed', self.paths['/plan'] and self.paths['/local_plan']),
                ('physical_goal_position', self.raw_robot is not None),
            ):
                if name in checks and not observed:
                    checks[name] = None
        instrumentation_complete = not any(d['errors'] for d in self.diagnostics.values())
        runtime_pass = all(value is True for value in checks.values()) and instrumentation_complete and not self.fatal_error
        topic_inventory = []
        try:
            topic_inventory = self.get_topic_names_and_types()
            self.event('topic_inventory', topics=topic_inventory)
        except Exception as exc:
            self.diagnostic_error('topic_inventory', exc)
        runtime_pass = runtime_pass and not self.fatal_error
        summary = {'navigation': status, 'error': error,
                   'dds_admission': self.dds_probe,
                   'mode': self.args.mode, 'readiness_reached': self.ready_reached,
                   'experiment_phase': 'NAVIGATION_ATTEMPTED' if self.goal_count else 'PRE_NAVIGATION',
                   'diagnostics': self.diagnostics, 'instrumentation_complete': instrumentation_complete, 'topic_inventory': topic_inventory,
                   'null_check_meaning': 'NOT_MEASURED / INCONCLUSIVE; not a runtime failure',
                   'automated_runtime_checks': checks,
                   'automated_runtime_checks_pass': runtime_pass,
                   'final_scene_accepted': False,
                   'visual_walking': 'MANUAL_CHECK_REQUIRED',
                   'crowd_stage': 'BLOCKED_PENDING_ONE_ACTOR_RUNTIME_AND_VISUAL_ACCEPTANCE',
                   'goal_count_sent': self.goal_count, 'goal_ids_observed': sorted(self.goal_ids),
                   'simulation_time_s': sim, 'wall_time_s': time.monotonic()-self.started_wall,
                   'goal_sim_time_s': self.args.goal_time if self.goal_count else None,
                   'final_odom_pose': self.robot,
                   'final_map_pose': final_map, 'final_world_pose': self.raw_robot,
                   'minimum_person_center_distance_m': self.min_distance,
                   'estimated_disc_clearance_m': None if self.min_distance is None else self.min_distance-0.28-0.35,
                   'clearance_definition': 'Planar centers; disk estimate uses robot 0.28m + human 0.35m. Not mesh contact.',
                   'recoveries': self.recoveries, 'no_valid_trajectories_log_messages': self.no_trajectories,
                   'failed_to_make_progress_log_messages': self.no_progress,
                   'angular_sign_reversals': self.reversals, 'max_stationary_spin_s': self.max_stationary_spin,
                   'absolute_rotation_rad': self.rotation,
                   'path_x_range_m': [min(self.path_x), max(self.path_x)] if self.path_x else None,
                   'speed_statistics': speeds,
                   'people_update_statistics': speed_stats([(t, 0.0, 0.0) for t in self.people_stamps]),
                   'people_wall_hz': ((len(self.people_wall_stamps)-1)/(self.people_wall_stamps[-1]-self.people_wall_stamps[0]))
                   if len(self.people_wall_stamps) > 1 else None,
                   'gazebo_observed_speed_statistics': speed_stats(observed_velocities),
                   'observed_actor_pose_samples': len(self.pose_errors),
                   'max_actor_pose_error_m': max(self.pose_errors, default=None),
                   'critic_evaluation_samples': self.critic_samples,
                   'critic_nonzero_samples': self.critic_nonzero, 'critic_varied_samples': self.critic_varied,
                   'scan_samples_with_nearby_people': self.laser_observations,
                   'scan_samples_with_associated_returns': self.laser_associations,
                   'costmap_samples_with_people_in_window': self.costmap_observations,
                   'costmap_samples_with_associated_lethal_cells': self.costmap_associations,
                   'lidar_conclusion': 'Spatial associations only; inspect paired baseline and RViz before attributing returns to actors.',
                   'path_message_counts': dict(self.paths), 'real_time_factor_wall_observed': rtf,
                   'gazebo_gui_fps': None, 'gazebo_gui_fps_status': 'NOT_MEASURED',
                   'local_path_changes_due_to_people': 'NOT_PROVEN_BY_PATH_EXTENT_ALONE',
                   'accepted_parameters_match': self.actual == self.expected}
        (self.out/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
        self.events.close()
        print(json.dumps(summary, indent=2), flush=True)
        return runtime_pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--mode', choices=['baseline', 'static', 'actor'], default='actor')
    parser.add_argument('--observe-only', action='store_true')
    parser.add_argument('--goal-time', type=float, default=60.0)
    args, ros_args = parser.parse_known_args()
    if not math.isfinite(args.goal_time) or args.goal_time < 10:
        parser.error('--goal-time must be finite and at least 10 simulation seconds')
    rclpy.init(args=ros_args)
    node = Recorder(args)
    status, error = 'ERROR', None
    try:
        status = node.run()
    except KeyboardInterrupt:
        status, error = 'INTERRUPTED', 'User interrupted the experiment'
    except Exception as exc:
        error = str(exc)
    finally:
        try:
            runtime_pass = node.finish(status, error)
        finally:
            node.action.destroy()
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
    raise SystemExit(0 if runtime_pass or status == 'OBSERVATION_ONLY' else 1)


if __name__ == '__main__':
    main()
