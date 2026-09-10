"""Publish read-only RViz markers for the Video 1 social-navigation model."""

from __future__ import annotations

import math

import rclpy
from rcl_interfaces.msg import ParameterType
from rcl_interfaces.srv import GetParameters
from rclpy.node import Node
from social_nav_msgs.msg import Pedestrians
from visualization_msgs.msg import Marker, MarkerArray


PARAMETER_NAMES = (
    "FollowPath.ProxemicForce.scale",
    "FollowPath.ProxemicForce.comfort_distance",
    "FollowPath.ProxemicForce.sigma",
    "FollowPath.ProxemicForce.anisotropic_enabled",
    "FollowPath.ProxemicForce.front_scale",
    "FollowPath.ProxemicForce.side_scale",
    "FollowPath.ProxemicForce.back_scale",
    "FollowPath.ProxemicForce.min_heading_speed",
)


class SocialVisualizationNode(Node):
    """Mirror /people as non-interactive position, label and zone markers."""

    def __init__(self) -> None:
        super().__init__("social_visualization_node")
        self.parameters = None
        self.parameter_future = None
        self.last_logged_parameters = None
        self.marker_publisher = self.create_publisher(
            MarkerArray, "/museum/social_markers", 10
        )
        self.create_subscription(Pedestrians, "/people", self._people_cb, 10)
        self.parameter_client = self.create_client(
            GetParameters, "/controller_server/get_parameters"
        )
        self.create_timer(1.0, self._poll_parameters)
        self.get_logger().info(
            "Visualizing /people on /museum/social_markers; output is read-only"
        )

    def _poll_parameters(self) -> None:
        if self.parameter_future is not None:
            if not self.parameter_future.done():
                return
            try:
                response = self.parameter_future.result()
            except Exception as exc:
                self.get_logger().warning(
                    f"Could not read controller parameters: {exc}"
                )
                response = None
            self.parameter_future = None
            if response is not None and len(response.values) == len(PARAMETER_NAMES):
                values = response.values
                parsed = (
                    _parameter_double(values[0]),
                    _parameter_double(values[1]),
                    _parameter_double(values[2]),
                    _parameter_bool(values[3]),
                    _parameter_double(values[4]),
                    _parameter_double(values[5]),
                    _parameter_double(values[6]),
                    _parameter_double(values[7]),
                )
                if all(value is not None for value in parsed):
                    self.parameters = parsed
                    if parsed != self.last_logged_parameters:
                        self.last_logged_parameters = parsed
                        self.get_logger().info(
                            "Runtime ProxemicForce visualization: "
                            f"scale={parsed[0]:.1f}, comfort={parsed[1]:.2f}, "
                            f"sigma={parsed[2]:.2f}, anisotropic={parsed[3]}, "
                            f"front={parsed[4]:.2f}, side={parsed[5]:.2f}, "
                            f"rear={parsed[6]:.2f}, min_speed={parsed[7]:.2f}"
                        )

        if self.parameter_future is None and self.parameter_client.service_is_ready():
            request = GetParameters.Request()
            request.names = list(PARAMETER_NAMES)
            self.parameter_future = self.parameter_client.call_async(request)

    def _people_cb(self, msg: Pedestrians) -> None:
        output = MarkerArray()
        clear = Marker()
        clear.action = Marker.DELETEALL
        output.markers.append(clear)

        for index, person in enumerate(msg.pedestrians):
            speed = math.hypot(person.velocity.x, person.velocity.y)
            moving = self._is_anisotropic(speed)
            output.markers.append(self._position_marker(msg, person, index, moving))
            output.markers.append(self._text_marker(msg, person, index))
            zone = self._zone_marker(msg, person, index, moving)
            if zone is not None:
                output.markers.append(zone)

        self.marker_publisher.publish(output)

    def _is_anisotropic(self, speed: float) -> bool:
        if self.parameters is None:
            return False
        anisotropic = self.parameters[3]
        min_heading_speed = self.parameters[7]
        return anisotropic and speed >= min_heading_speed

    def _position_marker(self, msg, person, index: int, moving: bool) -> Marker:
        marker = _marker(msg, "people", index, Marker.SPHERE)
        marker.pose.position.x = person.pose.x
        marker.pose.position.y = person.pose.y
        marker.pose.position.z = 0.20
        marker.pose.orientation.w = 1.0
        marker.scale.x = 0.34
        marker.scale.y = 0.34
        marker.scale.z = 0.40
        if moving:
            _color(marker, 1.0, 0.50, 0.05, 0.95)
        else:
            _color(marker, 0.10, 0.75, 1.0, 0.95)
        return marker

    def _text_marker(self, msg, person, index: int) -> Marker:
        marker = _marker(msg, "people_ids", index, Marker.TEXT_VIEW_FACING)
        marker.pose.position.x = person.pose.x
        marker.pose.position.y = person.pose.y
        marker.pose.position.z = 0.85
        marker.pose.orientation.w = 1.0
        marker.scale.z = 0.38
        marker.text = person.identifier
        _color(marker, 0.95, 0.98, 1.0, 1.0)
        return marker

    def _zone_marker(self, msg, person, index: int, moving: bool):
        if self.parameters is None:
            return None
        comfort = self.parameters[1]
        marker = _marker(msg, "social_zones", index, Marker.CYLINDER)
        marker.pose.position.x = person.pose.x
        marker.pose.position.y = person.pose.y
        marker.pose.position.z = 0.035
        marker.scale.z = 0.035

        if not moving:
            marker.pose.orientation.w = 1.0
            marker.scale.x = 2.0 * comfort
            marker.scale.y = 2.0 * comfort
            _color(marker, 0.10, 0.65, 1.0, 0.18)
            return marker

        front_scale, side_scale, rear_scale = self.parameters[4:7]
        heading = math.atan2(person.velocity.y, person.velocity.x)
        front = comfort * front_scale
        rear = comfort * rear_scale
        center_offset = 0.5 * (front - rear)
        marker.pose.position.x += center_offset * math.cos(heading)
        marker.pose.position.y += center_offset * math.sin(heading)
        marker.pose.orientation.z = math.sin(heading / 2.0)
        marker.pose.orientation.w = math.cos(heading / 2.0)
        marker.scale.x = front + rear
        marker.scale.y = 2.0 * comfort * side_scale
        _color(marker, 1.0, 0.45, 0.05, 0.22)
        return marker


def _marker(msg, namespace: str, marker_id: int, marker_type: int) -> Marker:
    marker = Marker()
    marker.header = msg.header
    marker.ns = namespace
    marker.id = marker_id
    marker.type = marker_type
    marker.action = Marker.ADD
    return marker


def _color(marker: Marker, red: float, green: float, blue: float, alpha: float):
    marker.color.r = red
    marker.color.g = green
    marker.color.b = blue
    marker.color.a = alpha


def _parameter_double(value):
    if value.type != ParameterType.PARAMETER_DOUBLE:
        return None
    return value.double_value


def _parameter_bool(value):
    if value.type != ParameterType.PARAMETER_BOOL:
        return None
    return value.bool_value


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SocialVisualizationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
