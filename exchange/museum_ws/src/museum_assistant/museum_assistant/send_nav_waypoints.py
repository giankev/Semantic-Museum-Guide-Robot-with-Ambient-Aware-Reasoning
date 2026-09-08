import argparse
import math
import sys
import time

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateThroughPoses
from rclpy.action import ActionClient
from rclpy.node import Node


class NavWaypointsClient(Node):
    def __init__(self):
        super().__init__("send_nav_waypoints")
        self.client = ActionClient(
            self, NavigateThroughPoses, "navigate_through_poses"
        )

    def send(self, poses: list[tuple[float, float, float]], frame: str) -> int:
        if not self.client.wait_for_server(timeout_sec=15.0):
            print("NavigateThroughPoses action server is not available.")
            return 1

        goal = NavigateThroughPoses.Goal()
        stamp = self.get_clock().now().to_msg()
        for x, y, yaw in poses:
            pose = PoseStamped()
            pose.header.frame_id = frame
            pose.header.stamp = stamp
            pose.pose.position.x = x
            pose.pose.position.y = y
            pose.pose.position.z = 0.0
            pose.pose.orientation.z = math.sin(yaw / 2.0)
            pose.pose.orientation.w = math.cos(yaw / 2.0)
            goal.poses.append(pose)

        print("Waypoint route:")
        for index, (x, y, yaw) in enumerate(poses, start=1):
            print(
                f"  {index}: x={x:.2f}, y={y:.2f}, "
                f"yaw={math.degrees(yaw):+.1f} deg"
            )

        future = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        handle = future.result()
        if handle is None or not handle.accepted:
            print("Waypoint route rejected.")
            return 2

        print("Waypoint route accepted.")
        start = time.monotonic()
        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        elapsed = time.monotonic() - start
        result = result_future.result()
        if result is None:
            print(f"Waypoint route finished without a result after {elapsed:.1f}s.")
            return 3

        status = result.status
        if status == GoalStatus.STATUS_SUCCEEDED:
            print(f"Waypoint route succeeded in {elapsed:.1f}s.")
            return 0
        if status == GoalStatus.STATUS_ABORTED:
            print(f"Waypoint route aborted after {elapsed:.1f}s.")
            return 4
        if status == GoalStatus.STATUS_CANCELED:
            print(f"Waypoint route canceled after {elapsed:.1f}s.")
            return 5

        print(f"Waypoint route ended with status {status} after {elapsed:.1f}s.")
        return 6


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send one Nav2 NavigateThroughPoses route."
    )
    parser.add_argument(
        "--pose",
        action="append",
        nargs=3,
        metavar=("X", "Y", "YAW"),
        type=float,
        required=True,
        help="route pose in meters/radians; repeat for every waypoint",
    )
    parser.add_argument("--frame", default="map")
    args = parser.parse_args()

    rclpy.init()
    node = NavWaypointsClient()
    try:
        code = node.send([tuple(pose) for pose in args.pose], args.frame)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    sys.exit(code)


if __name__ == "__main__":
    main()
