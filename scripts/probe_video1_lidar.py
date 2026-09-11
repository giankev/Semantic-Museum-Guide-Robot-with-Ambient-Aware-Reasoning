#!/usr/bin/env python3
"""Stationary TIAGo positive LiDAR control; spawns/deletes only an audit box.

Run inside the POC container during --baseline --observe-only. Never moves the
robot. Rejects a moving robot and retains before/box/after sector measurements.
"""
import argparse
import json
import math
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from gazebo_msgs.srv import SpawnEntity, DeleteEntity
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    rclpy.init()
    node = Node('video1_lidar_positive_control')
    state = {}
    scans = []
    node.create_subscription(Odometry, '/ground_truth_odom', lambda m: state.update(odom=m), qos_profile_sensor_data)
    node.create_subscription(LaserScan, '/scan_raw', scans.append, qos_profile_sensor_data)
    spawn = node.create_client(SpawnEntity, '/spawn_entity')
    delete = node.create_client(DeleteEntity, '/delete_entity')
    def call(client, request):
        if not client.wait_for_service(timeout_sec=10):
            raise RuntimeError('Gazebo service unavailable')
        f = client.call_async(request)
        rclpy.spin_until_future_complete(node, f, timeout_sec=20)
        if not f.done():
            raise RuntimeError('Gazebo service timed out')
        response = f.result()
        if not response.success:
            raise RuntimeError(response.status_message)
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
        for scan in scans[-20:]:
            sector = [v for i, v in enumerate(scan.ranges)
                      if abs(scan.angle_min + i*scan.angle_increment) < .15 and math.isfinite(v)]
            result.append(dict(stamp=scan.header.stamp.sec + scan.header.stamp.nanosec*1e-9,
                finite=sum(math.isfinite(v) for v in scan.ranges), total=len(scan.ranges),
                nan=sum(math.isnan(v) for v in scan.ranges),
                positive_inf=sum(v == math.inf for v in scan.ranges),
                negative_inf=sum(v == -math.inf for v in scan.ranges),
                front_min=min(sector) if sector else None))
        return result
    report = {}
    spawned = False
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
        spawned = True
        report['box_world_pose'] = [x, y, a]
        report['expected_front_range_m'] = 2 - .202 - .2
        report['box_present'] = sample()
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if spawned:
            request = DeleteEntity.Request()
            request.name = 'video1_lidar_audit_box'
            call(delete, request)
            report['after'] = sample()
        Path(args.output).write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
