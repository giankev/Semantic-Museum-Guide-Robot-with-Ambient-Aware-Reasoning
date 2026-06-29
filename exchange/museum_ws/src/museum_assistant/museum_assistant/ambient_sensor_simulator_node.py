import json
from itertools import cycle

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class AmbientSensorSimulatorNode(Node):
    def __init__(self):
        super().__init__("ambient_sensor_simulator_node")
        self.publisher = self.create_publisher(String, "/museum/ambient_state", 10)
        self.events = cycle(
            [
                {
                    "room_id": "impressionism_hall",
                    "crowd_level": "high",
                    "noise_level": "medium",
                    "status": "open",
                },
                {
                    "room_id": "impressionism_hall",
                    "crowd_level": "low",
                    "noise_level": "low",
                    "status": "open",
                },
                {
                    "room_id": "kids_hall",
                    "crowd_level": "low",
                    "noise_level": "medium",
                    "status": "open",
                },
                {
                    "room_id": "temporary_exhibition",
                    "crowd_level": "low",
                    "noise_level": "low",
                    "status": "open",
                },
                {
                    "room_id": "temporary_exhibition",
                    "crowd_level": "low",
                    "noise_level": "low",
                    "status": "closed",
                },
            ]
        )
        self.timer = self.create_timer(3.0, self.publish_next_event)
        self.get_logger().info("Publishing scripted ambient state on /museum/ambient_state")

    def publish_next_event(self) -> None:
        event = next(self.events)
        msg = String()
        msg.data = json.dumps(event)
        self.publisher.publish(msg)
        self.get_logger().info(f"Published ambient event: {msg.data}")


def main(args=None):
    rclpy.init(args=args)
    node = AmbientSensorSimulatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
