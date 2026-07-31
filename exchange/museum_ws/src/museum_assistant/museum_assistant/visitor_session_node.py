"""ROS adapter from Gazebo model state to a minimal visitor session."""

import json
import math

import rclpy
from gazebo_msgs.msg import ModelStates
from rclpy.node import Node
from std_msgs.msg import String

from museum_assistant.visitor_session import VisitorSession


DEFAULT_VISITOR_MODEL_NAME = "visitor_marker"
DEFAULT_ROBOT_MODEL_NAME = "tiago"


class VisitorSessionNode(Node):
    def __init__(self):
        super().__init__("visitor_session_node")
        self.declare_parameter(
            "visitor_model_name",
            DEFAULT_VISITOR_MODEL_NAME,
        )
        self.declare_parameter(
            "robot_model_name",
            DEFAULT_ROBOT_MODEL_NAME,
        )
        self._visitor_model_name = self.get_parameter(
            "visitor_model_name"
        ).value
        self._robot_model_name = self.get_parameter(
            "robot_model_name"
        ).value

        self.visitor = VisitorSession(self._visitor_model_name)
        self.session_publisher = self.create_publisher(
            String,
            "/museum/session_state",
            10,
        )
        self.observation_publisher = self.create_publisher(
            String,
            "/museum/visitor_observation",
            10,
        )
        self.subscription = self.create_subscription(
            ModelStates,
            "/gazebo/model_states",
            self._handle_model_states,
            10,
        )
        self._session_announced = False
        self._robot_missing_announced = False
        self.get_logger().info(
            "Observing the configured visitor and robot on "
            "/gazebo/model_states"
        )

    def _handle_model_states(self, msg: ModelStates) -> None:
        session = self.visitor.observe(msg.name)
        if session is not None:
            output = String()
            output.data = json.dumps(session.to_dict())
            self.session_publisher.publish(output)

            if not self._session_announced:
                self.get_logger().info(
                    "Created active visitor session "
                    f"session_id={session.session_id} "
                    f"track_id={session.track_id}"
                )
                self._session_announced = True

        model_indices = {
            name: index
            for index, name in enumerate(msg.name)
            if index < len(msg.pose)
        }
        visitor_index = model_indices.get(self._visitor_model_name)
        if visitor_index is None:
            self._publish_observation(present=False)
            return

        robot_index = model_indices.get(self._robot_model_name)
        if robot_index is None:
            if not self._robot_missing_announced:
                self.get_logger().warning(
                    "Configured robot model is not available in "
                    "/gazebo/model_states"
                )
                self._robot_missing_announced = True
            return

        self._robot_missing_announced = False
        visitor_pose = msg.pose[visitor_index]
        robot_pose = msg.pose[robot_index]
        distance = math.hypot(
            visitor_pose.position.x - robot_pose.position.x,
            visitor_pose.position.y - robot_pose.position.y,
        )
        self._publish_observation(
            present=True,
            distance_to_robot=distance,
        )

    def _publish_observation(
        self,
        *,
        present: bool,
        distance_to_robot: float | None = None,
    ) -> None:
        output = String()
        output.data = json.dumps(
            self.visitor.observation(
                present=present,
                distance_to_robot=distance_to_robot,
            )
        )
        self.observation_publisher.publish(output)


def main(args=None):
    rclpy.init(args=args)
    node = VisitorSessionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
