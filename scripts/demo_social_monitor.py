#!/usr/bin/env python3
"""Focused read-only dashboard for Video 1 social navigation."""

from __future__ import annotations

import math
import os
import shutil
import sys

from nav_msgs.msg import Odometry
import rclpy
from rcl_interfaces.msg import ParameterType
from rcl_interfaces.srv import GetParameters
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from social_nav_msgs.msg import Pedestrians


RESET = "\033[0m"
CYAN = "\033[1;36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"

PARAMETER_NAMES = (
    "FollowPath.ProxemicForce.scale",
    "FollowPath.ProxemicForce.comfort_distance",
    "FollowPath.ProxemicForce.sigma",
    "FollowPath.ProxemicForce.anisotropic_enabled",
)
IGNORED_PERSON_IDS = frozenset({"visitor_1"})


class SocialMonitor(Node):
    def __init__(self) -> None:
        super().__init__("demo_social_monitor")
        self.people = []
        self.robot = None
        self.robot_speed = None
        self.robot_yaw = None
        self.proxemic_scale = None
        self.comfort_distance = None
        self.sigma = None
        self.anisotropic_enabled = None
        self.parameter_future = None
        self.use_color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
        self.create_subscription(Pedestrians, "/people", self._people_cb, 10)
        self.create_subscription(
            Odometry, "/museum/ground_truth_odom", self._odom_cb, 10
        )
        self.parameter_client = self.create_client(
            GetParameters, "/controller_server/get_parameters"
        )
        self.create_timer(1.0, self._poll_parameters)
        self.create_timer(0.25, self.render)

    def _people_cb(self, msg: Pedestrians) -> None:
        self.people = list(msg.pedestrians)

    def _odom_cb(self, msg: Odometry) -> None:
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        self.robot = (p.x, p.y)
        self.robot_yaw = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )
        v = msg.twist.twist.linear
        self.robot_speed = math.hypot(v.x, v.y)

    def _nearest(self):
        if self.robot is None or not self.people:
            return None
        rx, ry = self.robot
        candidates = []
        for person in self.people:
            if person.identifier in IGNORED_PERSON_IDS:
                continue
            dx = person.pose.x - rx
            dy = person.pose.y - ry
            distance = math.hypot(dx, dy)
            bearing = math.atan2(dy, dx)
            relative = _wrap(bearing - (self.robot_yaw or 0.0))
            candidates.append((distance, relative, bearing, person))
        return min(candidates, key=lambda item: item[0]) if candidates else None

    def _poll_parameters(self) -> None:
        if self.parameter_future is not None:
            if not self.parameter_future.done():
                return
            try:
                response = self.parameter_future.result()
            except Exception:
                response = None
            self.parameter_future = None
            if response is not None and len(response.values) == len(PARAMETER_NAMES):
                scale, comfort, sigma, anisotropic = response.values
                self.proxemic_scale = _parameter_double(scale)
                self.comfort_distance = _parameter_double(comfort)
                self.sigma = _parameter_double(sigma)
                self.anisotropic_enabled = _parameter_bool(anisotropic)

        if self.parameter_future is None and self.parameter_client.service_is_ready():
            request = GetParameters.Request()
            request.names = list(PARAMETER_NAMES)
            self.parameter_future = self.parameter_client.call_async(request)

    def render(self) -> None:
        width = max(55, min(100, shutil.get_terminal_size((90, 30)).columns))
        nearest = self._nearest()
        lines = [
            self._paint("=" * min(width, 64), CYAN),
            self._paint("TIAGO SOCIAL NAVIGATION - VIDEO 1", CYAN),
            self._paint("=" * min(width, 64), CYAN),
            "",
            self._paint("[ SOCIAL NAVIGATION ]", CYAN),
            f"People detected: {len(self.people)}",
            "",
            "ProxemicForce:",
            f"  scale: {_number(self.proxemic_scale, 1)}",
            f"  comfort distance: {_number(self.comfort_distance, 2, 'm')}",
            f"  sigma: {_number(self.sigma, 2)}",
            f"  anisotropic: {_boolean(self.anisotropic_enabled)}",
            "",
            "TIAGo:",
            f"  speed: {_fmt(self.robot_speed, 'm/s')}",
            f"  heading: {_deg(self.robot_yaw)}",
        ]

        if nearest is None:
            lines.extend(
                [
                    "",
                    "Nearest relevant person:",
                    "  ID: —",
                    "  distance: —",
                    "  relative bearing: —",
                    "  orientation: —",
                    "  speed: —",
                    "  assessment: waiting for /people and odometry",
                ]
            )
        else:
            distance, relative, _bearing, person = nearest
            status, color = _status(
                distance, self.comfort_distance, self.sigma
            )
            person_speed = math.hypot(person.velocity.x, person.velocity.y)
            lines.extend(
                [
                    "",
                    "Nearest relevant person:",
                    f"  ID: {person.identifier}",
                    f"  distance: {self._paint(f'{distance:.2f} m', color)}",
                    f"  relative bearing: {_deg(relative)}",
                    f"  orientation: {_deg(person.pose.theta)}",
                    f"  speed: {person_speed:.2f} m/s",
                    f"  assessment: {self._paint(status, color)}",
                ]
            )

        lines.extend(
            [
                "",
                "Assessment visualizes the critic's smooth distance weighting.",
                "Comfort distance is not a hard safety threshold.",
                self._paint("=" * min(width, 64), CYAN),
            ]
        )
        sys.stdout.write("\033[2J\033[H" + "\n".join(lines) + "\n")
        sys.stdout.flush()

    def _paint(self, text: str, color: str) -> str:
        return f"{color}{text}{RESET}" if self.use_color else text


def _status(distance: float, comfort_distance, sigma):
    if comfort_distance is None or sigma is None:
        return "WAITING FOR RUNTIME PARAMETERS", YELLOW
    if distance < comfort_distance:
        return "CLOSE", RED
    if distance <= comfort_distance + 3.0 * sigma:
        return "SOCIAL INFLUENCE", YELLOW
    return "CLEAR", GREEN


def _wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _deg(angle) -> str:
    if angle is None or not math.isfinite(angle):
        return "—"
    return f"{math.degrees(angle):+.1f} deg"


def _fmt(value, unit: str) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value:.2f} {unit}"


def _number(value, digits: int, unit: str = "") -> str:
    if value is None or not math.isfinite(value):
        return "—"
    suffix = f" {unit}" if unit else ""
    return f"{value:.{digits}f}{suffix}"


def _boolean(value) -> str:
    if value is None:
        return "—"
    return "true" if value else "false"


def _parameter_double(value):
    if value.type != ParameterType.PARAMETER_DOUBLE:
        return None
    return value.double_value


def _parameter_bool(value):
    if value.type != ParameterType.PARAMETER_BOOL:
        return None
    return value.bool_value


def main() -> None:
    rclpy.init()
    node = SocialMonitor()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
