import json
from itertools import cycle

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class UserRequestSimulatorNode(Node):
    def __init__(self):
        super().__init__("user_request_simulator_node")
        self.publisher = self.create_publisher(String, "/museum/user_request", 10)
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
        self.get_logger().info("Publishing scripted user requests on /museum/user_request")

    def publish_next_request(self) -> None:
        request = next(self.requests)
        msg = String()
        msg.data = json.dumps(request)
        self.publisher.publish(msg)
        self.get_logger().info(f"Published user request: {msg.data}")


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
