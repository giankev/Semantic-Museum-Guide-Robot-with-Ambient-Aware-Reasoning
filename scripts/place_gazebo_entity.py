#!/usr/bin/env python3
"""Place one Gazebo entity for a benchmark fixture."""

import argparse
import math

from gazebo_msgs.msg import EntityState
from gazebo_msgs.srv import SetEntityState
import rclpy
from rclpy.node import Node


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--x", required=True, type=float)
    parser.add_argument("--y", required=True, type=float)
    parser.add_argument("--yaw", default=0.0, type=float)
    parser.add_argument("--timeout", default=30.0, type=float)
    args = parser.parse_args()

    rclpy.init()
    node = Node("benchmark_entity_placement")
    client = node.create_client(SetEntityState, "/gazebo/set_entity_state")
    try:
        if not client.wait_for_service(timeout_sec=args.timeout):
            raise RuntimeError("/gazebo/set_entity_state did not become ready")
        request = SetEntityState.Request()
        request.state = EntityState()
        request.state.name = args.name
        request.state.reference_frame = "world"
        request.state.pose.position.x = args.x
        request.state.pose.position.y = args.y
        request.state.pose.orientation.z = math.sin(args.yaw / 2.0)
        request.state.pose.orientation.w = math.cos(args.yaw / 2.0)
        future = client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=args.timeout)
        response = future.result()
        if response is None or not response.success:
            message = response.status_message if response is not None else "timeout"
            raise RuntimeError(f"Gazebo entity placement failed: {message}")
        print(f"Placed {args.name} at x={args.x:.3f}, y={args.y:.3f}")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
