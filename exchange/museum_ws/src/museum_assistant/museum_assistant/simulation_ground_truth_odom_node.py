"""ROS adapter for explicitly opted-in simulation ground-truth odometry."""

from __future__ import annotations

from copy import deepcopy

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from tf2_ros import TransformBroadcaster

from .simulation_ground_truth_odom import (
    BASE_FRAME,
    ODOM_FRAME,
    POSE_COVARIANCE,
    TWIST_COVARIANCE,
    PlanarAlignment,
    is_stale,
    validate_sample,
    validate_timestamp,
)


class SimulationGroundTruthOdomNode(Node):
    """Publish aligned Gazebo odometry and its sole odom-to-base transform."""

    def __init__(self) -> None:
        super().__init__("simulation_ground_truth_odom")
        self.declare_parameter("enabled", False)
        self.declare_parameter("stale_timeout_sec", 0.5)
        if not self.get_parameter("enabled").value:
            raise RuntimeError("simulation ground-truth odometry requires enabled:=true")
        if not self.get_parameter("use_sim_time").value:
            raise RuntimeError("simulation ground-truth odometry requires use_sim_time:=true")

        timeout = float(self.get_parameter("stale_timeout_sec").value)
        if timeout <= 0.0:
            raise RuntimeError("stale_timeout_sec must be positive")
        self._stale_timeout_ns = round(timeout * 1_000_000_000)
        self._alignment: PlanarAlignment | None = None
        self._last_source_stamp_ns: int | None = None
        self._last_receive_ns: int | None = None
        self._stale_reported = False

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self._publisher = self.create_publisher(
            Odometry, "/museum/ground_truth_odom", qos
        )
        self._broadcaster = TransformBroadcaster(self)
        self.create_subscription(Odometry, "/ground_truth_odom", self._input, qos)
        self.create_timer(0.1, self._check_staleness)

    @staticmethod
    def _values(message: Odometry):
        position = message.pose.pose.position
        orientation = message.pose.pose.orientation
        linear = message.twist.twist.linear
        angular = message.twist.twist.angular
        return (
            (position.x, position.y, position.z),
            (orientation.x, orientation.y, orientation.z, orientation.w),
            (linear.x, linear.y, linear.z),
            (angular.x, angular.y, angular.z),
        )

    def _input(self, source: Odometry) -> None:
        position, quaternion, linear, angular = self._values(source)
        try:
            validate_sample(position, quaternion, linear, angular)
            stamp_ns = validate_timestamp(
                source.header.stamp.sec,
                source.header.stamp.nanosec,
                self._last_source_stamp_ns,
            )
        except ValueError as error:
            self.get_logger().error(f"Rejecting invalid ground-truth odometry: {error}")
            return

        if self._alignment is None:
            self._alignment = PlanarAlignment.from_pose(position, quaternion)
            self.get_logger().info("Captured deterministic world-to-odom alignment")
        aligned_position, aligned_quaternion = self._alignment.apply(
            position, quaternion
        )

        output = Odometry()
        output.header.stamp = source.header.stamp
        output.header.frame_id = ODOM_FRAME
        output.child_frame_id = BASE_FRAME
        output.pose.pose.position.x, output.pose.pose.position.y, output.pose.pose.position.z = aligned_position
        orientation = output.pose.pose.orientation
        orientation.x, orientation.y, orientation.z, orientation.w = aligned_quaternion
        output.pose.covariance = POSE_COVARIANCE
        output.twist.twist = deepcopy(source.twist.twist)
        output.twist.covariance = TWIST_COVARIANCE
        self._publisher.publish(output)

        transform = TransformStamped()
        transform.header = output.header
        transform.child_frame_id = BASE_FRAME
        transform.transform.translation.x = aligned_position[0]
        transform.transform.translation.y = aligned_position[1]
        transform.transform.translation.z = aligned_position[2]
        transform.transform.rotation = output.pose.pose.orientation
        self._broadcaster.sendTransform(transform)

        self._last_source_stamp_ns = stamp_ns
        self._last_receive_ns = self.get_clock().now().nanoseconds
        self._stale_reported = False

    def _check_staleness(self) -> None:
        if self._stale_reported or self._last_receive_ns is None:
            return
        if is_stale(
            self.get_clock().now().nanoseconds,
            self._last_receive_ns,
            self._stale_timeout_ns,
        ):
            self._stale_reported = True
            self.get_logger().error(
                "Ground-truth odometry input is stale; output remains stopped"
            )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = SimulationGroundTruthOdomNode()
        rclpy.spin(node)
    except RuntimeError as error:
        rclpy.logging.get_logger("simulation_ground_truth_odom").fatal(str(error))
        raise
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
