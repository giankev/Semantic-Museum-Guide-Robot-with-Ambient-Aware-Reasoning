from pathlib import Path

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node


class SemanticGraphNode(Node):
    def __init__(self):
        super().__init__("semantic_graph_node")
        self.declare_parameter("semantic_map", "")
        semantic_map = self.get_parameter("semantic_map").get_parameter_value().string_value

        if semantic_map:
            map_path = Path(semantic_map)
        else:
            share_dir = Path(get_package_share_directory("museum_assistant"))
            map_path = share_dir / "config" / "semantic_map.yaml"

        self.semantic_map = self._load_semantic_map(map_path)
        self._log_summary(map_path)

    def _load_semantic_map(self, map_path: Path) -> dict:
        with map_path.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream) or {}

    def _log_summary(self, map_path: Path) -> None:
        rooms = self.semantic_map.get("rooms", [])
        artworks = self.semantic_map.get("artworks", [])

        self.get_logger().info(f"Loaded semantic map: {map_path}")
        self.get_logger().info(
            "Rooms: " + ", ".join(room.get("name", room.get("id", "unknown")) for room in rooms)
        )
        self.get_logger().info(
            "Artworks: "
            + ", ".join(artwork.get("title", artwork.get("id", "unknown")) for artwork in artworks)
        )


def main(args=None):
    rclpy.init(args=args)
    node = SemanticGraphNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
