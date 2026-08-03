import argparse
import math
import sys
import time

import rclpy
from action_msgs.msg import GoalStatus
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node


class NavGoalClient(Node):
    def __init__(self):
        super().__init__("send_nav_goal")
        self.client = ActionClient(self, NavigateToPose, "navigate_to_pose")

    def send_goal(self, x: float, y: float, yaw: float, frame: str) -> int:
        if not self.client.wait_for_server(timeout_sec=10.0):
            print("NavigateToPose action server is not available.")
            return 1

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.frame_id = frame
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.pose.position.x = x
        goal_msg.pose.pose.position.y = y
        goal_msg.pose.pose.position.z = 0.0
        goal_msg.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal_msg.pose.pose.orientation.w = math.cos(yaw / 2.0)

        send_future = self.client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, send_future)
        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            print("Goal rejected.")
            return 2

        print(f"Goal accepted: frame={frame}, x={x:.3f}, y={y:.3f}, yaw={yaw:.3f}")
        start_time = time.monotonic()
        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        elapsed = time.monotonic() - start_time
        result = result_future.result()
        if result is None:
            print(f"Goal finished without a result after {elapsed:.1f}s.")
            return 3

        status = result.status
        if status == GoalStatus.STATUS_SUCCEEDED:
            print(f"Goal succeeded in {elapsed:.1f}s.")
            return 0
        if status == GoalStatus.STATUS_ABORTED:
            print(f"Goal aborted after {elapsed:.1f}s.")
            return 4
        if status == GoalStatus.STATUS_CANCELED:
            print(f"Goal canceled after {elapsed:.1f}s.")
            return 5

        print(f"Goal finished with status code {status} after {elapsed:.1f}s.")
        return 6


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a Nav2 NavigateToPose goal.")
    parser.add_argument("--x", type=float, required=True, help="Goal x position in meters")
    parser.add_argument("--y", type=float, required=True, help="Goal y position in meters")
    parser.add_argument("--yaw", type=float, default=0.0, help="Goal yaw in radians")
    parser.add_argument("--frame", default="map", help="Goal frame id")
    args = parser.parse_args()

    rclpy.init()
    node = NavGoalClient()
    try:
        exit_code = node.send_goal(args.x, args.y, args.yaw, args.frame)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
