"""ROS adapter from deterministic reasoning decisions to physical routes."""

import json

from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from museum_assistant.semantic_graph import load_semantic_graph
from museum_assistant.semantic_route_dispatch import (
    ReasoningRouteDispatcher,
    SemanticRouteResolver,
)


class SemanticRouteDispatcherNode(Node):
    def __init__(self):
        super().__init__("semantic_route_dispatcher")
        share = get_package_share_directory("museum_assistant")
        defaults = {
            "semantic_map_path": f"{share}/config/semantic_map.yaml",
            "semantic_routes_path": (
                f"{share}/config/supplied_museum_semantic_routes.yaml"
            ),
            "routes_path": f"{share}/config/supplied_museum_routes.yaml",
            "layout_path": (
                f"{share}/config/supplied_museum_room_layout.yaml"
            ),
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

        graph = load_semantic_graph(
            self.get_parameter("semantic_map_path").value
        )
        resolver = SemanticRouteResolver.from_files(
            self.get_parameter("semantic_routes_path").value,
            graph,
            self.get_parameter("routes_path").value,
            self.get_parameter("layout_path").value,
        )
        self.dispatcher = ReasoningRouteDispatcher(resolver)
        self.route_publisher = self.create_publisher(
            String, "/museum/supplied_route_request", 10
        )
        self.response_subscription = self.create_subscription(
            String,
            "/museum/assistant_response",
            self._handle_response,
            10,
        )
        mapping_text = ", ".join(
            f"{room}->{route.route}"
            for room, route in resolver.mappings().items()
        )
        self.get_logger().info(
            f"Validated supplied-museum semantic routes: {mapping_text}"
        )

    def _handle_response(self, msg: String) -> None:
        try:
            decision = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warning(
                f"Ignoring malformed assistant-response JSON: {exc}"
            )
            return

        outcome = self.dispatcher.prepare(decision)
        if not outcome.dispatched:
            self.get_logger().warning(
                "Did not dispatch assistant response: "
                f"request_id={decision.get('request_id') if isinstance(decision, dict) else None} "
                f"reason={outcome.reason}"
            )
            return

        route_msg = String()
        route_msg.data = json.dumps(outcome.route_request)
        self.route_publisher.publish(route_msg)
        request = outcome.route_request
        self.get_logger().info(
            "Dispatched exactly one supplied-museum route request: "
            f"request_id={request['request_id']} "
            f"selected_room={request['selected_room']} "
            f"route={request['route']}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = SemanticRouteDispatcherNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
