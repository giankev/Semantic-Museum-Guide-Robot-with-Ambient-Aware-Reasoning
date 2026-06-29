import rclpy
from rclpy.node import Node


class CliNode(Node):
    def __init__(self):
        super().__init__("cli_node")
        self.get_logger().info("Museum assistant CLI placeholder is ready.")
        self.get_logger().info("Later this node will accept visitor requests and dispatch reasoning goals.")
        self.get_logger().info("For now, launch semantic_graph_node and sensor_simulator_node to test the stack.")


def main(args=None):
    rclpy.init(args=args)
    node = CliNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
