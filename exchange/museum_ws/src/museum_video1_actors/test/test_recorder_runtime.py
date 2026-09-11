"""Real Humble API regression tests; run inside museum-tiago:humble."""
from concurrent.futures import Future
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[3]
sys.path.insert(0, str(PACKAGE/'scripts'))
import rclpy
from rclpy.node import Node
from rclpy.logging import LoggingSeverity
from rclpy.qos import ReliabilityPolicy
from rcl_interfaces.msg import Log
from nav_msgs.msg import OccupancyGrid, Odometry
from sensor_msgs.msg import LaserScan
from social_nav_msgs.msg import Pedestrians
from gazebo_msgs.srv import GetEntityState
import record_demo


class RecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        args = SimpleNamespace(output=self.directory.name, mode='actor', goal_time=60., observe_only=False)
        with patch.object(record_demo, 'get_package_share_directory',
                          return_value=str(PACKAGE.parent/'museum_assistant')):
            self.node = record_demo.Recorder(args)

    def tearDown(self):
        self.node.events.close()
        self.node.action.destroy()
        self.node.destroy_node()
        self.directory.cleanup()

    def callback(self, topic, msg):
        next(s.callback for s in self.node.subscriptions if s.topic_name == topic)(msg)

    def test_construct_real_node_without_inherited_property_collision(self):
        self.assertIsInstance(self.node, Node)
        self.assertTrue(self.node.get_parameter('use_sim_time').value)
        self.assertEqual(self.node.now(), 0.0)
        self.assertEqual(set(self.node.lifecycle_clients), set(record_demo.LIFECYCLES))
        self.assertGreater(len(list(self.node.subscriptions)), 0)

    def test_dynamic_tf_uses_short_sensor_queue_and_static_tf_stays_latched(self):
        from rclpy.qos import DurabilityPolicy
        dynamic = next(s for s in self.node.subscriptions if s.topic_name == '/tf')
        static = next(s for s in self.node.subscriptions if s.topic_name == '/tf_static')
        self.assertEqual(dynamic.qos_profile.depth, 5)
        self.assertEqual(dynamic.qos_profile.reliability, ReliabilityPolicy.BEST_EFFORT)
        self.assertEqual(static.qos_profile.durability, DurabilityPolicy.TRANSIENT_LOCAL)

    def test_runtime_bt_parameter_must_match_manifest_before_goal(self):
        self.node.nav2_manifest = {'bt_timeout_ms': 200}
        self.node.actual = self.node.expected
        with patch.object(self.node, 'now', return_value=60.), \
             patch.object(self.node, 'nav_active', return_value=True):
            self.assertFalse(self.node.ready())
            self.node.bt_timeout_actual = 20
            with self.assertRaisesRegex(RuntimeError, 'BT action timeout differs'):
                self.node.ready()
        self.assertEqual(self.node.goal_count, 0)

    def test_effective_nav2_changes_only_ack_timeout(self):
        import json
        import yaml
        source = (REPO/'scripts/start_video1_animated_demo.sh').read_text()
        start = source.index("python3 -c 'import hashlib,json,pathlib,sys,yaml")
        command = shlex.split(source[start:source.index('>"${RUN_DIR}/nav2_manifest.json"', start)])
        generator = command[command.index('-c')+1]
        accepted = PACKAGE.parent/'museum_assistant/config/nav2_supplied_anisotropic.yaml'
        original = yaml.safe_load(accepted.read_text())
        output = Path(self.directory.name)/'nav2.yaml'
        for timeout in (20, 200):
            result = subprocess.run([sys.executable, '-c', generator, str(accepted), str(output), str(timeout)],
                                    capture_output=True, text=True, check=True)
            manifest = json.loads(result.stdout)
            effective = yaml.safe_load(output.read_text())
            self.assertEqual(effective['bt_navigator']['ros__parameters']['default_server_timeout'], timeout)
            effective['bt_navigator']['ros__parameters']['default_server_timeout'] = 20
            self.assertEqual(effective, original)
            self.assertEqual(manifest['bt_timeout_ms'], timeout)
            self.assertEqual(len(manifest['changes']), int(timeout != 20))

    def test_warn_numeric_and_byte_levels_with_real_humble_constant(self):
        # Reproduce int >= bytes even on generators that expose int constants.
        with patch.object(record_demo, 'Log', SimpleNamespace(WARN=b'\x1e')):
            for level in (int(LoggingSeverity.WARN), b'\x1e', 40):
                msg = SimpleNamespace(level=level, stamp=SimpleNamespace(sec=0, nanosec=0),
                                      name='test', msg='warning')
                self.callback('/rosout', msg)
        real = Log()
        try:
            real.level = 30
        except (AssertionError, TypeError):
            real.level = b'\x1e'
        real.msg = 'real generated message'
        self.callback('/rosout', real)
        self.assertEqual(self.node.diagnostics['/rosout']['errors'], 0)
        self.assertEqual(self.node.diagnostics['/rosout']['samples'], 4)
        self.assertEqual((Path(self.directory.name)/'observations.jsonl').read_text().count('ros_log'), 4)

    def test_optional_bad_messages_are_explicit_and_do_not_stop_recorder(self):
        self.callback('/rosout', SimpleNamespace(level=None, msg='bad'))
        grid = OccupancyGrid()  # zero resolution / no cells
        self.callback('/local_costmap/costmap', grid)
        self.assertIsNone(self.node.fatal_error)
        self.assertEqual(self.node.diagnostics['/rosout']['status'], 'ERROR')
        self.assertEqual(self.node.diagnostics['/local_costmap/costmap']['errors'], 1)
        self.node.step()

    def test_critical_bad_people_fails_clearly_outside_callback(self):
        self.callback('/people', Pedestrians())  # no frame
        with self.assertRaisesRegex(RuntimeError, 'Critical input /people'):
            self.node.step()

    def test_all_negative_infinity_scan_blocks_blind_navigation_even_without_people(self):
        scan = LaserScan()
        scan.header.frame_id = 'base_laser_link'
        scan.header.stamp.sec = 1
        scan.range_min, scan.range_max = .05, 25.0
        scan.ranges = [float('-inf')] * 666
        self.callback('/scan_raw', scan)
        self.assertEqual(self.node.scan_health['status'], 'NO_FINITE_RETURNS')
        self.assertIsNone(self.node.scan_health['last_usable_sim'])
        with patch.object(self.node, 'now', return_value=7.0):
            with self.assertRaisesRegex(RuntimeError, 'LiDAR has no finite returns'):
                self.node.step()
        self.assertEqual(self.node.goal_count, 0)
        scan.header.stamp.sec = 8
        scan.ranges = [1.6] * 666
        self.callback('/scan_raw', scan)
        self.assertEqual(self.node.scan_health['status'], 'USABLE')
        self.assertEqual(self.node.scan_health['last_usable_sim'], 8.0)

    def test_failed_service_future_releases_pending_and_can_retry(self):
        future = Future()
        client = SimpleNamespace(service_is_ready=lambda: True, call_async=lambda _: future)
        self.node.request('actor', client, None, self.node.actor_observation)
        future.set_exception(RuntimeError('transport failure'))
        self.assertNotIn('actor', self.node.pending)
        self.assertEqual(self.node.diagnostics['actor']['errors'], 1)
        self.assertIsNone(self.node.fatal_error)
        next_future = Future()
        client.call_async = lambda _: next_future
        self.node.request('actor', client, None, self.node.actor_observation)
        self.assertIs(self.node.pending['actor'], next_future)
        next_future.set_result(GetEntityState.Response(success=False))
        self.assertEqual(self.node.diagnostics['actor']['errors'], 2)

    def test_real_gazebo_entity_response_uses_response_header(self):
        from social_nav_msgs.msg import Pedestrian
        raw = Pedestrians()
        raw.header.frame_id = 'world'
        raw.header.stamp.sec = 10
        person = Pedestrian()
        person.identifier = 'walker_1'
        person.pose.x = 2.
        person.pose.y = 8.
        person.velocity.x = 0.2
        raw.pedestrians = [person]
        self.node.on_actor_state(raw)
        response = GetEntityState.Response(success=True)
        response.header.stamp.sec = 10
        response.state.pose.position.x = 2.
        response.state.pose.position.y = 8.
        self.node.actor_observation(response)
        self.assertEqual(self.node.pose_errors, [0.])

    def test_one_goal_and_success_result_without_optional_topics(self):
        from action_msgs.msg import GoalStatus
        times = iter([50., 50., 60.])
        sent = []
        result_future = Future()
        result_future.set_result(SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED))
        goal_handle = SimpleNamespace(accepted=True, get_result_async=lambda: result_future)
        def send(goal, feedback_callback):
            sent.append(goal)
            future = Future()
            future.set_result(goal_handle)
            return future
        with patch.object(self.node, 'check_dds_admission'), \
             patch.object(self.node, 'ready', return_value=True), \
             patch.object(self.node, 'now', side_effect=lambda: next(times, 60.)), \
             patch.object(self.node.action, 'send_goal_async', side_effect=send):
            self.assertEqual(self.node.run(), 'SUCCESS')
        self.assertEqual(len(sent), 1)
        self.assertEqual(self.node.goal_count, 1)
        self.assertEqual(sent[0].pose.pose.position.x, 0.)
        self.assertEqual(sent[0].pose.pose.position.y, 16.)

    def test_dds_exhaustion_is_reported_before_readiness(self):
        (Path(self.directory.name)/'runtime.log').write_text(
            'gzserver: Failed to find a free participant index for domain 107\n')
        with self.assertRaisesRegex(RuntimeError, 'DDS participant exhaustion'):
            self.node.poll()
        self.assertEqual(self.node.dds_probe['status'], 'FAIL')
        self.assertEqual(self.node.goal_count, 0)

    def test_failed_post_readiness_admission_never_sends_goal(self):
        with patch.object(self.node, 'ready', return_value=True), \
             patch.object(self.node, 'check_dds_admission', side_effect=RuntimeError('DDS admission failed')), \
             patch.object(self.node.action, 'send_goal_async') as send:
            with self.assertRaisesRegex(RuntimeError, 'DDS admission failed'):
                self.node.run()
            send.assert_not_called()
        self.assertFalse(self.node.ready_reached)

    def test_service_timeout_releases_pending(self):
        future = Future()
        self.node.pending['test'] = future
        self.node.pending_times['test'] = 0
        self.node.poll()
        self.assertTrue(future.cancelled())
        self.assertNotIn('test', self.node.pending)

    def test_no_readiness_at_zero_clock_or_stale_lifecycle(self):
        self.node.states = {n: 3 for n in record_demo.LIFECYCLES}
        self.node.state_times = {n: 0 for n in record_demo.LIFECYCLES}
        self.assertFalse(self.node.nav_active())
        with patch.object(self.node, 'now', return_value=0):
            self.assertFalse(self.node.ready())
            self.node.on_odom(Odometry())
            self.assertIsNone(self.node.robot_time)

    def test_clock_reset_is_not_silently_throttled(self):
        self.node.robot_time = 5
        odom = Odometry()
        odom.header.stamp.sec = 4
        with patch.object(self.node, 'now', return_value=4):
            with self.assertRaisesRegex(RuntimeError, 'backwards'):
                self.node.on_odom(odom)
        self.node.last_sim = 5
        with patch.object(self.node, 'now', return_value=4):
            with self.assertRaisesRegex(RuntimeError, 'clock reset'):
                self.node.step()

    def test_sensor_subscribers_accept_best_effort_publishers(self):
        for sub in self.node.subscriptions:
            if sub.topic_name in ('/people', '/scan_raw', '/museum/ground_truth_odom', '/evaluation'):
                self.assertEqual(sub.qos_profile.reliability, ReliabilityPolicy.BEST_EFFORT)

    def test_action_future_exception_is_clear(self):
        future = Future()
        future.set_exception(ValueError('broken result'))
        with self.assertRaisesRegex(RuntimeError, 'ROS action operation failed: broken result'):
            self.node.wait_future(future)

    def test_pre_navigation_summary_does_not_claim_runtime_failures(self):
        import json
        with patch('builtins.print'):
            self.assertFalse(self.node.finish('ERROR', 'startup failed'))
        summary = json.loads((Path(self.directory.name)/'summary.json').read_text())
        self.assertEqual(summary['experiment_phase'], 'PRE_NAVIGATION')
        self.assertTrue(all(v is None for v in summary['automated_runtime_checks'].values()))
        self.assertFalse(summary['final_scene_accepted'])


class ShellTests(unittest.TestCase):
    def test_runtime_failure_keeps_scene_but_preparation_failure_stops_it(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'scripts').mkdir()
            launcher = root/'scripts/start_video1_animated_demo.sh'
            shutil.copy(REPO/'scripts/start_video1_animated_demo.sh', launcher)
            (root/'bin').mkdir()
            docker = root/'bin/docker'
            docker.write_text(r"""#!/usr/bin/python3
import os, sys
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as log:
    log.write(repr(args)+'\n')
if args[:2] == ['container', 'inspect']:
    sys.exit(1)
if args[0] == 'exec':
    if 'record_demo.py' in args[-1]:
        sys.exit(7)
    if os.environ['FAIL_BUILD'] == '1' and 'colcon build' in args[-1]:
        sys.exit(8)
""")
            docker.chmod(0o755)
            git = root/'bin/git'
            git.write_text('#!/bin/sh\necho test-revision\n')
            git.chmod(0o755)
            calls = root/'calls'
            env = dict(os.environ, PATH=str(root/'bin')+':'+os.environ['PATH'],
                       CALLS=str(calls), DISPLAY=':1')
            for fail_build, code, stopped in [('0', 7, False), ('1', 8, True)]:
                calls.write_text('')
                result = subprocess.run(['bash', str(launcher), '--headless'],
                                        env=dict(env, FAIL_BUILD=fail_build),
                                        stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, code, result.stderr.decode())
                self.assertEqual("['stop'," in calls.read_text(), stopped)
                if not stopped:
                    import ast
                    run = next(ast.literal_eval(line) for line in calls.read_text().splitlines()
                               if ast.literal_eval(line)[0] == 'run')
                    self.assertIn('--network=host', run)
                    self.assertIn('ROS_DOMAIN_ID=107', run)
                    self.assertNotIn('ROS_LOCALHOST_ONLY=1', run)
                    self.assertFalse(any('CYCLONEDDS_URI=' in arg for arg in run))
                    self.assertIn('Simulation remains open', result.stderr.decode())

    def test_gui_uses_stable_x_access_and_transparent_verbose_wrapper(self):
        source = (REPO/'scripts/start_video1_animated_demo.sh').read_text()
        self.assertIn('xhost +local:docker', source)
        self.assertNotIn('video1.Xauthority', source)
        self.assertIn('/tmp/.X11-unix:/tmp/.X11-unix:rw', source)
        self.assertIn('LIBGL_ALWAYS_SOFTWARE=0', source)
        start = source.index('docker exec "${CONTAINER}" python3 -c \'import pathlib,shlex,shutil,sys')
        command = shlex.split(source[start:source.index('\n\n', start)])
        generator = command[command.index('-c')+1]
        with tempfile.TemporaryDirectory() as directory:
            fake_client = Path(directory)/'real-client'
            fake_client.write_text('#!/bin/sh\nprintf "%s\\n" "$@" "$GAZEBO_MODEL_PATH" "$LIBGL_ALWAYS_SOFTWARE"\n')
            fake_client.chmod(0o755)
            wrapper_dir = Path(directory)/'bin'
            with patch('shutil.which', return_value=str(fake_client)), \
                 patch.object(sys, 'argv', ['-c', directory, 'software']):
                exec(compile(generator, 'wrapper_generator', 'exec'), {})
            for program, renderer in [('gzclient', '0'), ('gzserver', '1')]:
                result = subprocess.run([str(wrapper_dir/program), '--test-argument'],
                    env=dict(os.environ, GAZEBO_MODEL_PATH='scoped-PAL-models', LIBGL_ALWAYS_SOFTWARE='0'),
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), ['--verbose', '--test-argument', 'scoped-PAL-models', renderer])

    def test_version_probe_ignores_gazebo_cli_exit_255_but_checks_pkg_config(self):
        source = (REPO/'scripts/start_video1_animated_demo.sh').read_text()
        self.assertNotIn('gazebo --version', source)
        self.assertNotIn('gzserver --version', source)
        line = next(line for line in source.splitlines() if "bash -c 'version=" in line)
        command = shlex.split(line)[-1]
        with tempfile.TemporaryDirectory() as directory:
            for name in ('gazebo', 'gzserver'):
                path = Path(directory)/name
                path.write_text('#!/bin/sh\necho "Gazebo 11.10.2"\nexit 255\n')
                path.chmod(0o755)
            pkg = Path(directory)/'pkg-config'
            env = dict(os.environ, PATH=directory+':'+os.environ['PATH'])
            for version, exit_code, expected in [('11.10.2', 0, 0), ('12.0', 0, 1), ('11.10.2', 1, 1)]:
                pkg.write_text(f'#!/bin/sh\necho {version}\nexit {exit_code}\n')
                pkg.chmod(0o755)
                result = subprocess.run(['bash', '-c', command], env=env, capture_output=True)
                self.assertEqual(result.returncode, expected, result.stderr)


if __name__ == '__main__':
    unittest.main()
