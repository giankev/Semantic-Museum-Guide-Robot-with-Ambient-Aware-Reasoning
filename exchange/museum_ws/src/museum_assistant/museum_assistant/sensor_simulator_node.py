import json
from itertools import cycle

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class SensorSimulatorNode(Node):
    def __init__(self):
        super().__init__("sensor_simulator_node")
        self.publisher = self.create_publisher(String, "museum/ambient_status", 10)
        self.samples = cycle(
            [
                {"room": "entrance_hall", "crowd_level": 0.2, "noise_level": 0.3, "status": "open"},
                {"room": "impressionist_gallery", "crowd_level": 0.7, "noise_level": 0.5, "status": "open"},
                {"room": "temporary_exhibition", "crowd_level": 0.4, "noise_level": 0.2, "status": "open"},
                {"room": "kids_lab", "crowd_level": 0.6, "noise_level": 0.8, "status": "guided_activity"},
            ]
        )
        self.timer = self.create_timer(2.0, self.publish_sample)
        self.get_logger().info("Publishing simulated ambient status on /museum/ambient_status")

    def publish_sample(self):
        msg = String()
        msg.data = json.dumps(next(self.samples))
        self.publisher.publish(msg)
        self.get_logger().info(f"Ambient status: {msg.data}")


def main(args=None):
    rclpy.init(args=args)
    node = SensorSimulatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
