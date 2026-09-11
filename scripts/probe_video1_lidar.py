#!/usr/bin/env python3
"""Stationary TIAGo positive LiDAR control; spawns/deletes only an audit box.

Run inside the POC container during --baseline --observe-only. Never moves the
robot. Rejects a moving robot and retains before/box/after sector measurements.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from gazebo_msgs.srv import SpawnEntity, DeleteEntity, GetEntityState
from nav_msgs.msg import Odometry, OccupancyGrid
from sensor_msgs.msg import LaserScan
from social_nav_msgs.msg import Pedestrians


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--actors', action='store_true', help='Also compare stationary and moving walk.dae Actors')
    args = parser.parse_args()
    rclpy.init()
    node = Node('video1_lidar_positive_control')
    state = {}
    scans = []
    node.create_subscription(Odometry, '/ground_truth_odom', lambda m: state.update(odom=m), qos_profile_sensor_data)
    node.create_subscription(LaserScan, '/scan_raw',
        lambda m: scans.append((m, state.get('actor'), state.get('odom'))), qos_profile_sensor_data)
    node.create_subscription(OccupancyGrid, '/local_costmap/costmap',
                             lambda m: state.update(costmap=m), qos_profile_sensor_data)
    node.create_subscription(Pedestrians, '/museum/video1/actor_states',
                             lambda m: state.update(actor=m), qos_profile_sensor_data)
    spawn = node.create_client(SpawnEntity, '/spawn_entity')
    delete = node.create_client(DeleteEntity, '/delete_entity')
    entity = node.create_client(GetEntityState, '/gazebo/get_entity_state')
    def call(client, request, allow_missing=False):
        if not client.wait_for_service(timeout_sec=10):
            raise RuntimeError('Gazebo service unavailable')
        f = client.call_async(request)
        rclpy.spin_until_future_complete(node, f, timeout_sec=20)
        if not f.done():
            raise RuntimeError('Gazebo service timed out')
        response = f.result()
        if not response.success and not allow_missing:
            raise RuntimeError(response.status_message)
        return response
    def sample():
        scans.clear()
        end = time.monotonic() + 8
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=.05)
        if not scans or 'odom' not in state:
            raise RuntimeError('No scan/odometry input')
        o = state['odom']
        if math.hypot(o.twist.twist.linear.x, o.twist.twist.linear.y) > .01 or abs(o.twist.twist.angular.z) > .02:
            raise RuntimeError('Robot is moving: run --observe-only')
        result = []
        for scan, actor_msg, odom in scans[-20:]:
            sector = [v for i, v in enumerate(scan.ranges)
                      if abs(scan.angle_min + i*scan.angle_increment) < .15 and math.isfinite(v)]
            item = dict(stamp=scan.header.stamp.sec + scan.header.stamp.nanosec*1e-9,
                finite=sum(math.isfinite(v) for v in scan.ranges), total=len(scan.ranges),
                nan=sum(math.isnan(v) for v in scan.ranges),
                positive_inf=sum(v == math.inf for v in scan.ranges),
                negative_inf=sum(v == -math.inf for v in scan.ranges),
                front_min=min(sector) if sector else None)
            if actor_msg and actor_msg.pedestrians:
                actor = actor_msg.pedestrians[0]
                item['actor'] = dict(x=actor.pose.x, y=actor.pose.y,
                    vx=actor.velocity.x, vy=actor.velocity.y,
                    stamp=actor_msg.header.stamp.sec + actor_msg.header.stamp.nanosec*1e-9)
            result.append(item)
        last_scan = scans[-1][0]
        result[-1]['ranges'] = [v if math.isfinite(v) else None for v in last_scan.ranges]
        result[-1]['angle_min'] = last_scan.angle_min
        result[-1]['angle_increment'] = last_scan.angle_increment
        if 'costmap' in state:
            grid = state['costmap']
            result[-1]['costmap'] = dict(frame=grid.header.frame_id,
                stamp=grid.header.stamp.sec+grid.header.stamp.nanosec*1e-9,
                origin=[grid.info.origin.position.x, grid.info.origin.position.y],
                resolution=grid.info.resolution, width=grid.info.width,
                height=grid.info.height, data=list(grid.data))
        return result
    report = {}
    spawned_name = None
    def remove_owned():
        nonlocal spawned_name
        request = DeleteEntity.Request()
        request.name = spawned_name
        call(delete, request)
        spawned_name = None
    try:
        report['before'] = sample()
        p = state['odom'].pose.pose
        q = p.orientation
        a = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        x, y = p.position.x+2*math.cos(a), p.position.y+2*math.sin(a)
        request = SpawnEntity.Request()
        request.name = 'video1_lidar_audit_box'
        request.xml = f'''<sdf version="1.6"><model name="video1_lidar_audit_box"><static>true</static>
        <pose>{x} {y} 0.75 0 0 {a}</pose><link name="box">
        <collision name="collision"><geometry><box><size>0.4 1 1.5</size></box></geometry></collision>
        <visual name="visual"><geometry><box><size>0.4 1 1.5</size></box></geometry></visual>
        </link></model></sdf>'''
        call(spawn, request)
        spawned_name = request.name
        report['box_world_pose'] = [x, y, a]
        report['expected_front_range_m'] = 2 - .202 - .2
        report['box_present'] = sample()
        remove_owned()
        report['after_box'] = sample()
        if args.actors:
            asset = next(Path('/usr/share').glob('gazebo-11*/media/models/walk.dae'))
            for phase in ('stationary_actor', 'moving_actor'):
                request = SpawnEntity.Request()
                request.name = 'video1_walker_1'
                if phase == 'stationary_actor':
                    # Freeze the actual plugin pose and animation clock: a
                    # native constant-waypoint walking script still has root
                    # motion and is not a stationary control.
                    motion = f'''<plugin name="audit_actor" filename="libvideo1_actor.so">
                    <cx>{x-.7}</cx><cy>{y}</cy><rx>.7</rx><ry>.7</ry><omega>.5</omega><phase>0</phase>
                    <stationary>true</stationary></plugin>'''
                else:
                    motion = f'''<plugin name="audit_actor" filename="libvideo1_actor.so">
                    <cx>{x}</cx><cy>{y}</cy><rx>.7</rx><ry>.7</ry><omega>.5</omega><phase>0</phase>
                    </plugin>'''
                request.xml = f'''<sdf version="1.6"><actor name="video1_walker_1">
                <skin><filename>{asset}</filename><scale>1</scale></skin>
                <animation name="walking"><filename>{asset}</filename><scale>1</scale>
                <interpolate_x>true</interpolate_x></animation>{motion}</actor></sdf>'''
                existing = GetEntityState.Request()
                existing.name, existing.reference_frame = request.name, 'world'
                if call(entity, existing, allow_missing=True).success:
                    raise RuntimeError('Actor already exists; use a baseline observation run')
                # gazebo_ros SpawnEntity rejects <actor>; Classic's native
                # factory explicitly supports it. Use an argv list, no shell.
                subprocess.run(['gz', 'topic', '-p', '/gazebo/default/factory',
                    '-m', 'sdf: '+json.dumps(request.xml)],
                    check=True, timeout=15, capture_output=True, text=True)
                spawned_name = request.name
                deadline = time.monotonic() + 15
                while not call(entity, existing, allow_missing=True).success:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Native Actor factory did not create the Actor')
                    rclpy.spin_once(node, timeout_sec=.1)
                report[phase] = sample()
                request = GetEntityState.Request()
                request.name, request.reference_frame = spawned_name, 'world'
                response = call(entity, request)
                report[phase+'_measured_pose'] = [response.state.pose.position.x,
                                                 response.state.pose.position.y,
                                                 response.state.pose.position.z]
                measured = [s['actor'] for s in report[phase] if 'actor' in s]
                if not measured:
                    raise RuntimeError('Actor state stream missing during the control')
                if phase == 'stationary_actor':
                    if any(math.hypot(s['vx'], s['vy']) > 1e-6 for s in measured) or math.hypot(
                            response.state.pose.position.x-x, response.state.pose.position.y-y) > .05:
                        raise RuntimeError('Stationary Actor control moved; restart Gazebo after rebuilding its plugin')
                elif max(math.hypot(s['vx'], s['vy']) for s in measured) < .1:
                    raise RuntimeError('Moving Actor control did not move')
                remove_owned()
                state.pop('actor', None)
            report['after_actors'] = sample()
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if spawned_name:
            try:
                remove_owned()
            except Exception as exc:
                report['cleanup_error'] = str(exc)
        Path(args.output).write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
        node.destroy_node()
        rclpy.shutdown()
    raise SystemExit(1 if 'error' in report or 'cleanup_error' in report else 0)


if __name__ == '__main__':
    main()
