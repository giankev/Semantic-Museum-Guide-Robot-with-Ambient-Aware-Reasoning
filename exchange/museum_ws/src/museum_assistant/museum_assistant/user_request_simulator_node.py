import json
from itertools import cycle

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class UserRequestSimulatorNode(Node):
    def __init__(self):
        super().__init__("user_request_simulator_node")
        self.publisher = self.create_publisher(String, "/museum/user_request", 10)
        self.session_subscription = self.create_subscription(
            String,
            "/museum/session_state",
            self._handle_session_state,
            10,
        )
        self.active_session_id = None
        self.requests = cycle(
            [
                {
                    "request_id": "req_001",
                    "intent": "recommend",
                    "constraints": {
                        "style": "impressionism",
                        "avoid_crowd": True,
                    },
                },
                {
                    "request_id": "req_002",
                    "intent": "recommend",
                    "constraints": {
                        "child_friendly": True,
                    },
                },
                {
                    "request_id": "req_003",
                    "intent": "recommend_and_prepare_navigation",
                    "constraints": {
                        "wheelchair_accessible": True,
                    },
                },
                {
                    "request_id": "req_004",
                    "intent": "recommend",
                    "constraints": {
                        "style": "surrealist_clockwork",
                        "avoid_crowd": True,
                    },
                },
                {
                    "request_id": "req_005",
                    "intent": "dance",
                    "constraints": {},
                },
            ]
        )
        self.timer = self.create_timer(4.0, self.publish_next_request)
        self.get_logger().info(
            "Publishing scripted user requests on /museum/user_request"
        )

    def publish_next_request(self) -> None:
        request = dict(next(self.requests))
        if self.active_session_id is not None:
            request["session_id"] = self.active_session_id

        msg = String()
        msg.data = json.dumps(request)
        self.publisher.publish(msg)
        self.get_logger().info(f"Published user request: {msg.data}")

    def _handle_session_state(self, msg: String) -> None:
        try:
            session = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning("Ignoring invalid session-state JSON")
            return

        session_id = session.get("session_id")
        if session.get("state") != "active" or not isinstance(session_id, str):
            return

        if session_id != self.active_session_id:
            self.active_session_id = session_id
            self.get_logger().info(
                f"Using active session_id={self.active_session_id}"
            )


def main(args=None):
    rclpy.init(args=args)
    node = UserRequestSimulatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
