"""ROS adapter from Gazebo model state to a minimal visitor session."""

import json

import rclpy
from gazebo_msgs.msg import ModelStates
from rclpy.node import Node
from std_msgs.msg import String

from museum_assistant.visitor_session import VisitorSession


SIMULATOR_MODEL_NAME = "visitor_marker"


class VisitorSessionNode(Node):
    def __init__(self):
        super().__init__("visitor_session_node")
        self.visitor = VisitorSession(SIMULATOR_MODEL_NAME)
        self.publisher = self.create_publisher(
            String,
            "/museum/session_state",
            10,
        )
        self.subscription = self.create_subscription(
            ModelStates,
            "/gazebo/model_states",
            self._handle_model_states,
            10,
        )
        self._session_announced = False
        self.get_logger().info(
            "Waiting for the configured simulated visitor on "
            "/gazebo/model_states"
        )

    def _handle_model_states(self, msg: ModelStates) -> None:
        session = self.visitor.observe(msg.name)
        if session is None:
            return

        output = String()
        output.data = json.dumps(session.to_dict())
        self.publisher.publish(output)

        if not self._session_announced:
            self.get_logger().info(
                "Created active visitor session "
                f"session_id={session.session_id} "
                f"track_id={session.track_id}"
            )
            self._session_announced = True


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
