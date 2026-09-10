#!/usr/bin/env python3
"""Fresh-process DDS admission and communication check after stack readiness."""
import argparse
import json
import os
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from controller_manager_msgs.srv import ListControllers
from nav_msgs.msg import OccupancyGrid
from rosgraph_msgs.msg import Clock
from social_nav_msgs.msg import Pedestrians


def probe(mode, timeout):
    evidence = {'status': 'FAIL', 'pid': os.getpid(),
                'domain': os.environ.get('ROS_DOMAIN_ID', '0'),
                'participant_created': False, 'clock_advancing': False,
                'map_received': False, 'people_received': mode == 'baseline',
                'controller_manager_responded': False}
    node = None
    try:
        rclpy.init(args=[])
        # A new OS process is essential: another Node in the recorder's context
        # would reuse its DDS participant and would not exercise admission.
        node = Node('video1_dds_admission_probe')
        evidence['participant_created'] = True
        stamps = []
        def clock(msg):
            t = msg.clock.sec + msg.clock.nanosec / 1e9
            if t > 0:
                stamps.append(t)
                evidence['clock_advancing'] = t > stamps[0]
        def map_received(msg):
            evidence['map_received'] = (msg.info.width > 0 and msg.info.height > 0
                and msg.info.resolution > 0 and len(msg.data) == msg.info.width*msg.info.height)
        def people(msg):
            identifiers = [p.identifier for p in msg.pedestrians]
            evidence['people_received'] = (identifiers == ['walker_1'] if mode == 'actor'
                                           else len(identifiers) == 10)
        node.create_subscription(Clock, '/clock', clock, qos_profile_sensor_data)
        node.create_subscription(OccupancyGrid, '/map', map_received,
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        if mode != 'baseline':
            node.create_subscription(Pedestrians, '/people', people, qos_profile_sensor_data)
        client = node.create_client(ListControllers, '/controller_manager/list_controllers')
        future = None
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if future is None and client.service_is_ready():
                future = client.call_async(ListControllers.Request())
            if future is not None and future.done():
                response = future.result()  # caught below; a failed RPC is not a pass
                evidence['controller_manager_responded'] = response is not None
            if all(evidence[key] for key in ('participant_created', 'clock_advancing',
                    'map_received', 'people_received', 'controller_manager_responded')):
                evidence['status'] = 'PASS'
                break
        if evidence['status'] != 'PASS':
            evidence['error'] = 'New participant could not communicate with all required stack endpoints before timeout'
    except Exception as exc:
        evidence['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--mode', choices=('actor', 'static', 'baseline'), default='actor')
    parser.add_argument('--timeout', type=float, default=20.0)
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        parser.error('--timeout must be in (0, 60] wall seconds')
    evidence = probe(args.mode, args.timeout)
    Path(args.output).write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps(evidence), flush=True)
    return 0 if evidence['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
