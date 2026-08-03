import json

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String

from museum_assistant.semantic_graph import SemanticMapError, load_semantic_graph


class SemanticGraphNode(Node):
    def __init__(self):
        super().__init__("semantic_graph_node")
        self.declare_parameter("semantic_map_path", "")
        semantic_map_path = self.get_parameter("semantic_map_path").value

        if not semantic_map_path:
            share_dir = get_package_share_directory("museum_assistant")
            semantic_map_path = f"{share_dir}/config/semantic_map.yaml"

        try:
            self.semantic_graph = load_semantic_graph(semantic_map_path)
        except (OSError, SemanticMapError, KeyError) as exc:
            self.get_logger().error(f"Failed to load semantic map: {exc}")
            raise

        self._log_summary(semantic_map_path)
        self._log_demo_queries()
        self.ambient_subscription = self.create_subscription(
            String,
            "/museum/ambient_state",
            self._handle_ambient_state,
            10,
        )
        self.get_logger().info("Subscribed to /museum/ambient_state")

    def _log_summary(self, map_path: str) -> None:
        self.get_logger().info(f"Loaded semantic map: {map_path}")
        self.get_logger().info(f"Rooms: {len(self.semantic_graph.room_ids())}")
        self.get_logger().info(f"Artworks: {len(self.semantic_graph.artwork_ids())}")
        self.get_logger().info(f"Graph nodes: {self.semantic_graph.graph.number_of_nodes()}")
        self.get_logger().info(f"Graph edges: {self.semantic_graph.graph.number_of_edges()}")

    def _log_demo_queries(self) -> None:
        impressionism = self.semantic_graph.recommend_room(
            style="impressionism",
            avoid_crowd=True,
        )
        child_friendly = self.semantic_graph.recommend_room(child_friendly=True)
        self.get_logger().info(
            "Demo recommendation, impressionism avoiding crowd: "
            f"{impressionism['reason']}"
        )
        self.get_logger().info(
            "Demo recommendation, child-friendly room: "
            f"{child_friendly['reason']}"
        )

    def _handle_ambient_state(self, msg: String) -> None:
        try:
            event = json.loads(msg.data)
            room_id = event["room_id"]
            updated_state = self.semantic_graph.update_room_state(
                room_id=room_id,
                status=event.get("status"),
                crowd_level=event.get("crowd_level"),
                noise_level=event.get("noise_level"),
            )
        except json.JSONDecodeError as exc:
            self.get_logger().warning(f"Ignoring invalid ambient JSON: {exc}")
            return
        except KeyError as exc:
            self.get_logger().warning(f"Ignoring ambient event missing field: {exc}")
            return
        except ValueError as exc:
            self.get_logger().warning(f"Ignoring invalid ambient event: {exc}")
            return

        self.get_logger().info(f"Updated ambient room state: {updated_state}")
        recommendation = self.semantic_graph.recommend_room(
            style="impressionism",
            avoid_crowd=True,
        )
        selected = recommendation["selected_room"]
        selected_id = selected["id"] if selected else "none"
        self.get_logger().info(
            "After ambient update, recommendation for "
            "style=impressionism, avoid_crowd=True: "
            f"selected_room={selected_id}; {recommendation['reason']}"
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
