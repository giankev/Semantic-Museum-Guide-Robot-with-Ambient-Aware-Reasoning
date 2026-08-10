import json

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String

from museum_assistant.contracts import ReasoningDecision
from museum_assistant.reasoning import DeterministicReasoner
from museum_assistant.semantic_graph import SemanticMapError, load_semantic_graph


class ReasoningNode(Node):
    def __init__(self):
        super().__init__("reasoning_node")
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

        self.reasoner = DeterministicReasoner(self.semantic_graph)
        self.response_publisher = self.create_publisher(
            String,
            "/museum/assistant_response",
            10,
        )
        self.scene_graph_publisher = self.create_publisher(
            String,
            "/museum/scene_graph",
            10,
        )
        self.ambient_subscription = self.create_subscription(
            String,
            "/museum/ambient_state",
            self._handle_ambient_state,
            10,
        )
        self.request_subscription = self.create_subscription(
            String,
            "/museum/user_request",
            self._handle_user_request,
            10,
        )
        self.get_logger().info(f"Loaded semantic map: {semantic_map_path}")
        self.get_logger().info("Subscribed to /museum/ambient_state")
        self.get_logger().info("Subscribed to /museum/user_request")
        self.get_logger().info(
            "Publishing assistant responses on /museum/assistant_response"
        )
        self._publish_scene_graph()

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
        self._publish_scene_graph()

    def _handle_user_request(self, msg: String) -> None:
        try:
            request = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            response = ReasoningDecision.invalid(
                reason=f"Request data is not valid JSON: {exc}"
            ).to_dict()
            self._publish_response(response)
            self.get_logger().warning(response["reason"])
            return

        response = self.reasoner.handle_request(request)
        self._publish_response(response)
        self._publish_scene_graph()
        self.get_logger().info(
            "Handled request "
            f"request_id={response.get('request_id')} "
            f"intent={response.get('intent')} "
            f"selected_room={response.get('selected_room')} "
            f"skill={response.get('skill')} "
            f"reason={response.get('reason')}"
        )

    def _publish_response(self, response: dict) -> None:
        msg = String()
        msg.data = json.dumps(response)
        self.response_publisher.publish(msg)

    def _publish_scene_graph(self) -> None:
        msg = String()
        msg.data = json.dumps(self.semantic_graph.snapshot())
        self.scene_graph_publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ReasoningNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
