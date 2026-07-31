"""Publish Gazebo museum markers as a standard simulated people stream."""

import math

import rclpy
from gazebo_msgs.msg import ModelStates
from rclpy.node import Node
from social_nav_msgs.msg import Pedestrian, Pedestrians

from museum_assistant.simulated_people import (
    MODEL_TO_PUBLIC_ID,
    people_from_model_positions,
)


class SimulatedPeopleNode(Node):
    def __init__(self):
        super().__init__("simulated_people_node")
        self._publisher = self.create_publisher(Pedestrians, "/people", 10)
        self._subscription = self.create_subscription(
            ModelStates,
            "/gazebo/model_states",
            self._handle_model_states,
            10,
        )
        self._previous_positions = {}
        self.get_logger().info(
            "Publishing simulated Gazebo people on /people in the map frame"
        )

    def _handle_model_states(self, msg: ModelStates) -> None:
        model_positions = {}
        for name, pose in zip(msg.name, msg.pose):
            if name not in MODEL_TO_PUBLIC_ID:
                continue
            quaternion = pose.orientation
            yaw = math.atan2(
                2.0
                * (
                    quaternion.w * quaternion.z
                    + quaternion.x * quaternion.y
                ),
                1.0
                - 2.0
                * (
                    quaternion.y * quaternion.y
                    + quaternion.z * quaternion.z
                ),
            )
            model_positions[name] = (
                pose.position.x,
                pose.position.y,
                yaw,
            )

        now = self.get_clock().now()
        samples, self._previous_positions = people_from_model_positions(
            model_positions,
            timestamp=now.nanoseconds / 1e9,
            previous_positions=self._previous_positions,
        )

        output = Pedestrians()
        output.header.stamp = now.to_msg()
        output.header.frame_id = "map"
        for sample in samples:
            pedestrian = Pedestrian()
            pedestrian.identifier = sample.identifier
            pedestrian.pose.x = sample.x
            pedestrian.pose.y = sample.y
            pedestrian.pose.theta = sample.theta
            pedestrian.velocity.x = sample.vx
            pedestrian.velocity.y = sample.vy
            pedestrian.velocity.theta = 0.0
            output.pedestrians.append(pedestrian)
        self._publisher.publish(output)


def main(args=None):
    rclpy.init(args=args)
    node = SimulatedPeopleNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
