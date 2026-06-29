import argparse
import math
import sys
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.node import Node


def quaternion_to_yaw(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


class NavPoseCapture(Node):
    def __init__(self, expected_frame: str):
        super().__init__("capture_nav_pose")
        self.expected_frame = expected_frame
        self.pose_msg = None
        self.subscription = self.create_subscription(
            PoseWithCovarianceStamped,
            "/amcl_pose",
            self._pose_callback,
            10,
        )

    def _pose_callback(self, msg: PoseWithCovarianceStamped) -> None:
        if self.pose_msg is None:
            self.pose_msg = msg

    def wait_for_pose(self, timeout_sec: float):
        deadline = time.monotonic() + timeout_sec
        while rclpy.ok() and self.pose_msg is None and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        return self.pose_msg


def format_nav_pose(name: str, msg: PoseWithCovarianceStamped) -> str:
    pose = msg.pose.pose
    orientation = pose.orientation
    yaw = quaternion_to_yaw(
        orientation.x,
        orientation.y,
        orientation.z,
        orientation.w,
    )
    return "\n".join(
        [
            f"{name}:",
            "  nav_pose:",
            f"    x: {pose.position.x:.3f}",
            f"    y: {pose.position.y:.3f}",
            f"    yaw: {yaw:.3f}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture the current AMCL pose as a semantic nav_pose YAML snippet."
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Room or artwork id for the snippet key",
    )
    parser.add_argument(
        "--frame",
        default="map",
        help="Expected frame id for /amcl_pose. No transform is applied.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for one /amcl_pose message",
    )
    args = parser.parse_args()

    rclpy.init()
    node = NavPoseCapture(args.frame)
    try:
        msg = node.wait_for_pose(args.timeout)
        if msg is None:
            print("No /amcl_pose message received before timeout.", file=sys.stderr)
            sys.exit(1)

        frame_id = msg.header.frame_id
        if frame_id != args.frame:
            print(
                f"Received /amcl_pose in frame '{frame_id}', expected '{args.frame}'. "
                "No transform was applied.",
                file=sys.stderr,
            )
            sys.exit(2)

        print(format_nav_pose(args.name, msg))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
