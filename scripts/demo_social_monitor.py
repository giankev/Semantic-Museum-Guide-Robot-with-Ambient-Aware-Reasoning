#!/usr/bin/env python3
"""Focused read-only dashboard for Video 1 social navigation."""

from __future__ import annotations

import math
import os
import shutil
import sys

from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from social_nav_msgs.msg import Pedestrians


RESET = "\033[0m"
CYAN = "\033[1;36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
COMFORT_DISTANCE_M = 3.0


class SocialMonitor(Node):
    def __init__(self) -> None:
        super().__init__("demo_social_monitor")
        self.people = []
        self.robot = None
        self.robot_speed = None
        self.robot_yaw = None
        self.use_color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
        self.create_subscription(Pedestrians, "/people", self._people_cb, 10)
        self.create_subscription(
            Odometry, "/museum/ground_truth_odom", self._odom_cb, 10
        )
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
            dx = person.pose.x - rx
            dy = person.pose.y - ry
            distance = math.hypot(dx, dy)
            bearing = math.atan2(dy, dx)
            relative = _wrap(bearing - (self.robot_yaw or 0.0))
            candidates.append((distance, relative, bearing, person))
        return min(candidates, key=lambda item: item[0])

    def render(self) -> None:
        width = max(55, min(100, shutil.get_terminal_size((90, 30)).columns))
        nearest = self._nearest()
        lines = [
            self._paint("=" * min(width, 64), CYAN),
            self._paint("TIAGO SOCIAL NAVIGATION - VIDEO 1", CYAN),
            self._paint("=" * min(width, 64), CYAN),
            "",
            f"People detected: {len(self.people) if self.people else '—'}",
            f"Social comfort target: {COMFORT_DISTANCE_M:.1f} m",
            f"TIAGo speed: {_fmt(self.robot_speed, 'm/s')}",
            f"TIAGo heading: {_deg(self.robot_yaw)}",
        ]

        if nearest is None:
            lines.extend(
                [
                    "Nearest person: —",
                    "Distance: —",
                    "Relative bearing: —",
                    "Decision: waiting for /people and odometry",
                ]
            )
        else:
            distance, relative, bearing, person = nearest
            status, color = _status(distance)
            person_speed = math.hypot(person.velocity.x, person.velocity.y)
            lines.extend(
                [
                    "",
                    self._paint("[ NEAREST PERSON ]", CYAN),
                    f"ID: {person.identifier}",
                    f"Distance: {self._paint(f'{distance:.2f} m', color)}",
                    f"World bearing: {_deg(bearing)}",
                    f"Relative bearing: {_deg(relative)}",
                    f"NPC orientation: {_deg(person.pose.theta)}",
                    f"NPC speed: {person_speed:.2f} m/s",
                    f"Decision: {self._paint(status, color)}",
                ]
            )

        lines.extend(
            [
                "",
                "Interpretation:",
                "  > 3.0 m  = socially clear",
                "  2.5-3.0m = caution / trajectory reshaping",
                "  < 2.5 m  = too close; strong avoidance expected",
                "",
                "Static NPCs => proxemic avoidance is isotropic in the critic.",
                self._paint("=" * min(width, 64), CYAN),
            ]
        )
        sys.stdout.write("\033[2J\033[H" + "\n".join(lines) + "\n")
        sys.stdout.flush()

    def _paint(self, text: str, color: str) -> str:
        return f"{color}{text}{RESET}" if self.use_color else text


def _status(distance: float):
    if distance >= COMFORT_DISTANCE_M:
        return "CLEAR - keep route", GREEN
    if distance >= 2.5:
        return "CAUTION - reshape trajectory", YELLOW
    return "TOO CLOSE - strong social avoidance", RED


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


def main() -> None:
    rclpy.init()
    node = SocialMonitor()
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
