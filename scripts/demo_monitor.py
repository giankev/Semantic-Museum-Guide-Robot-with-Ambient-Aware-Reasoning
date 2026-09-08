#!/usr/bin/env python3
"""Read-only ANSI dashboard for the TIAGo museum-guide demo."""

from __future__ import annotations

import argparse
from functools import partial
import json
import math
import os
import shutil
import sys
from typing import Any

from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from social_nav_msgs.msg import Pedestrians
from std_msgs.msg import String


TOPICS = {
    "engagement": "/museum/engagement_state",
    "request": "/museum/user_request",
    "response": "/museum/assistant_response",
    "session": "/museum/session_state",
    "ambient": "/museum/ambient_state",
    "observation": "/museum/visitor_observation",
    "escort": "/museum/escort_state",
    "navigation": "/museum/navigation_result",
    "scene": "/museum/scene_graph",
    # This existing bridge topic exposes the route while navigation is active.
    "route_request": "/museum/supplied_route_request",
}

RESET = "\033[0m"
CYAN = "\033[1;36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"


class DemoMonitor(Node):
    """Cache existing topic payloads and redraw one terminal screen."""

    def __init__(self, show_graph: bool) -> None:
        super().__init__("demo_monitor")
        self.show_graph = show_graph
        self.data: dict[str, dict[str, Any]] = {name: {} for name in TOPICS}
        self.user_text = ""
        self.people: list[tuple[str, float, float, float, float]] | None = None
        self.robot_position: tuple[float, float] | None = None
        self.robot_speed: float | None = None
        self.use_color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
        self.cursor_hidden = False

        self.create_subscription(
            String, "/museum/user_text", self._store_user_text, 10
        )
        for name, topic in TOPICS.items():
            self.create_subscription(
                String, topic, partial(self._store_json, name), 10
            )
        self.create_subscription(Pedestrians, "/people", self._store_people, 10)
        self.create_subscription(
            Odometry,
            "/museum/ground_truth_odom",
            self._store_robot_position,
            10,
        )
        self.create_timer(0.25, self.render)
        self.render()

    def _store_user_text(self, message: String) -> None:
        self.user_text = message.data.strip()

    def _store_json(self, name: str, message: String) -> None:
        try:
            payload = json.loads(message.data)
        except (json.JSONDecodeError, TypeError):
            return
        if isinstance(payload, dict):
            self.data[name] = payload

    def _store_people(self, message: Pedestrians) -> None:
        self.people = [
            (
                person.identifier,
                person.pose.x,
                person.pose.y,
                person.velocity.x,
                person.velocity.y,
            )
            for person in message.pedestrians
        ]

    def _store_robot_position(self, message: Odometry) -> None:
        position = message.pose.pose.position
        self.robot_position = (position.x, position.y)
        velocity = message.twist.twist.linear
        speed = math.hypot(velocity.x, velocity.y)
        self.robot_speed = speed if math.isfinite(speed) else None

    def render(self) -> None:
        width = max(50, min(120, shutil.get_terminal_size((100, 40)).columns))
        d = self.data
        engagement = d["engagement"]
        request = d["request"]
        response = d["response"]
        session = d["session"]
        ambient = d["ambient"]
        escort = _current(d["escort"], response)
        navigation = _current(d["navigation"], response)
        route_request = _current(d["route_request"], response)
        preferences, destination = self._session_memory()

        selected_room = _first(
            response.get("selected_room"),
            escort.get("selected_room"),
            navigation.get("selected_room"),
            destination,
        )
        route = _first(
            route_request.get("route"),
            navigation.get("route"),
            response.get("route"),
        )
        visitor_distance = _first(
            escort.get("distance_to_robot"),
            d["observation"].get("distance_to_robot"),
        )
        session_id = self._session_id()
        session_display = (
            f"{session_id} ({session['state']})"
            if session_id and session.get("state")
            else session_id
        )
        people, moving, nearest, nearest_distance, nearest_speed = (
            self._social_navigation()
        )

        sections = (
            (
                "INTERACTION",
                (
                    ("State:", engagement.get("state")),
                    ("Confidence:", _number(engagement.get("person_confidence"))),
                    ("Distance:", _measure(engagement.get("distance_m"), "m")),
                    (
                        "Radial velocity:",
                        _measure(
                            engagement.get("radial_speed_mps"), "m/s", signed=True
                        ),
                    ),
                    ("Dwell:", _measure(engagement.get("dwell_s"), "s", 1)),
                ),
            ),
            (
                "LANGUAGE",
                (
                    ("Transcription:", self.user_text),
                    ("Intent:", request.get("intent")),
                    ("Constraints:", _mapping(request.get("constraints"))),
                ),
            ),
            (
                "REASONING",
                (
                    ("Selected room:", selected_room),
                    ("Skill:", response.get("skill")),
                    ("Reason:", response.get("reason")),
                    ("Route:", route),
                ),
            ),
            (
                "SESSION",
                (
                    ("Session:", session_display, session.get("state")),
                    ("Stored preferences:", _mapping(preferences)),
                    ("Remembered destination:", destination),
                ),
            ),
            (
                "AMBIENT",
                (
                    ("Room:", ambient.get("room_id")),
                    ("Crowd:", ambient.get("crowd_level")),
                    ("Noise:", ambient.get("noise_level")),
                    ("Status:", ambient.get("status")),
                ),
            ),
            (
                "ESCORT",
                (
                    ("State:", escort.get("state")),
                    ("Visitor distance:", _measure(visitor_distance, "m")),
                    ("Thresholds:", "resume <=2m | wait >3m | lost >=8m"),
                ),
            ),
            (
                "SOCIAL NAVIGATION",
                (
                    ("People:", people),
                    ("Moving:", moving),
                    ("Nearest considered bystander:", nearest),
                    ("Nearest distance:", _measure(nearest_distance, "m")),
                    ("Nearest speed:", _measure(nearest_speed, "m/s")),
                    ("TIAGo speed:", _measure(self.robot_speed, "m/s")),
                    ("Mode:", "ANISOTROPIC"),
                ),
            ),
            ("NAVIGATION", (("Status:", navigation.get("status")),)),
        )

        bar = "=" * min(60, width)
        lines = [
            self._paint(bar, CYAN),
            self._paint("TIAGO MUSEUM GUIDE - LIVE DEMO", CYAN),
            self._paint(bar, CYAN),
        ]
        for heading, fields in sections:
            lines.extend(("", self._paint(f"[ {heading} ]", CYAN)))
            for label, value, *tone in fields:
                color_key = tone[0] if tone else value
                lines.append(self._row(label, value, width, color_key))
        if self.show_graph:
            lines.extend(("", self._paint("[ ACTIVE SCENE GRAPH ]", CYAN)))
            lines.extend(self._scene_graph(selected_room, width))
        lines.append(self._paint(bar, CYAN))

        prefix = (
            "\033[2J\033[H\033[?25l"
            if not self.cursor_hidden
            else "\033[H\033[J"
        )
        self.cursor_hidden = True
        sys.stdout.write(prefix + "\n".join(lines) + "\n")
        sys.stdout.flush()

    def _session_id(self) -> Any:
        return _first(
            self.data["session"].get("session_id"),
            self.data["response"].get("session_id"),
            self.data["request"].get("session_id"),
        )

    def _session_memory(self) -> tuple[dict[str, Any], Any]:
        scene = self.data["scene"]
        session_id = self._session_id()
        node = _session_node(scene.get("nodes"), session_id)
        preferences = _preferences(node)
        request_constraints = self.data["request"].get("constraints")
        if not preferences and isinstance(request_constraints, dict):
            preferences = request_constraints
        destination = _destination(scene.get("edges"), session_id)
        if destination is None:
            destination = self.data["response"].get("selected_room")
        return preferences, destination

    def _scene_graph(self, selected_room: Any, width: int) -> list[str]:
        scene = self.data["scene"]
        nodes = scene.get("nodes")
        edges = scene.get("edges")
        session = _session_node(nodes, self._session_id())
        if not session:
            return ["(waiting for an active session in /museum/scene_graph)"]

        session_id = session.get("id")
        destination = _destination(edges, session_id)
        room_id = selected_room or destination
        room = next(
            (
                node
                for node in nodes
                if node.get("kind") == "room" and node.get("id") == room_id
            ),
            {},
        )
        items = []
        if destination:
            items.append(f"wants_to_reach -> {destination}")
        for label, field in (
            ("crowd", "crowd_level"),
            ("noise", "noise_level"),
            ("status", "status"),
        ):
            if room.get(field) is not None:
                items.append(f"{label}: {room[field]}")

        artworks = _artworks_in_room(nodes, edges, room_id)
        matching = self.data["response"].get("matching_artworks")
        if isinstance(matching, list) and matching:
            artworks = [artwork for artwork in artworks if artwork in matching]
        items.extend(f"artwork -> {artwork}" for artwork in artworks[:3])
        if len(artworks) > 3:
            items.append(f"artwork -> ... (+{len(artworks) - 3})")

        lines = [_truncate(str(session_id), width)]
        for index, item in enumerate(items):
            branch = "└──" if index == len(items) - 1 else "├──"
            lines.append(_truncate(f"{branch} {item}", width))
        return lines

    def _social_navigation(self) -> tuple[Any, Any, Any, Any, Any]:
        if self.people is None:
            return None, None, None, None, None
        speeds = [math.hypot(person[3], person[4]) for person in self.people]
        moving = sum(math.isfinite(speed) and speed >= 0.05 for speed in speeds)
        if self.robot_position is None:
            return len(self.people), moving, None, None, None

        candidates = []
        robot_x, robot_y = self.robot_position
        for person, speed in zip(self.people, speeds):
            identifier, x, y, _, _ = person
            if identifier == "visitor_1":
                continue
            distance = math.hypot(x - robot_x, y - robot_y)
            if math.isfinite(distance) and math.isfinite(speed):
                candidates.append((distance, identifier, speed))
        if not candidates:
            return len(self.people), moving, None, None, None
        distance, identifier, speed = min(candidates)
        return len(self.people), moving, identifier, distance, speed

    def _row(self, label: str, value: Any, width: int, tone: Any) -> str:
        text = _truncate(_display(value), max(8, width - len(label) - 1))
        return f"{label} {self._paint(text, _tone(tone))}"

    def _paint(self, text: str, color: str | None) -> str:
        return f"{color}{text}{RESET}" if self.use_color and color else text

    def restore_terminal(self) -> None:
        if self.cursor_hidden:
            sys.stdout.write("\033[?25h" + RESET + "\n")
            sys.stdout.flush()


def _current(payload: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    payload_id = payload.get("request_id")
    response_id = response.get("request_id")
    return {} if payload_id and response_id and payload_id != response_id else payload


def _first(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _display(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value).lower() if isinstance(value, bool) else str(value)


def _number(value: Any, digits: int = 2) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f"{value:.{digits}f}"


def _measure(
    value: Any, unit: str, digits: int = 2, signed: bool = False
) -> str | None:
    number = _number(value, digits)
    if number is not None and signed and value >= 0:
        number = "+" + number
    return f"{number} {unit}" if number is not None else None


def _mapping(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return ", ".join(
        f"{key}={_display(item)}" for key, item in sorted(value.items())
    ) or "{}"


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(1, width - 1)] + "…"


def _tone(value: Any) -> str | None:
    key = str(value).strip().lower()
    if key in {
        "accepted", "active", "arrived", "engaged", "escorting", "low",
        "open", "success", "succeeded",
    }:
        return GREEN
    if key in {
        "canceled", "disengaging", "medium", "passing",
        "potential_interaction", "waiting",
    }:
        return YELLOW
    if key in {
        "aborted", "closed", "error", "failed", "high", "invalid_request",
        "lost", "no_match", "rejected", "server_unavailable",
    }:
        return RED
    return None


def _session_node(nodes: Any, session_id: Any) -> dict[str, Any]:
    if not isinstance(nodes, list):
        return {}
    sessions = [
        node
        for node in nodes
        if isinstance(node, dict) and node.get("kind") == "session"
    ]
    if session_id is not None:
        return next((node for node in sessions if node.get("id") == session_id), {})
    return next((node for node in sessions if node.get("active") is True), {})


def _preferences(node: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "preferred_style": "style",
        "avoid_crowd": "avoid_crowd",
        "avoid_noise": "avoid_noise",
        "child_friendly": "child_friendly",
        "wheelchair_accessible": "wheelchair_accessible",
    }
    return {
        output: node[source]
        for source, output in fields.items()
        if source in node
    }


def _destination(edges: Any, session_id: Any) -> Any:
    if not isinstance(edges, list) or session_id is None:
        return None
    return next(
        (
            edge.get("target")
            for edge in edges
            if isinstance(edge, dict)
            and edge.get("source") == session_id
            and edge.get("relation") == "wants_to_reach"
        ),
        None,
    )


def _artworks_in_room(nodes: Any, edges: Any, room_id: Any) -> list[str]:
    if not isinstance(nodes, list) or not isinstance(edges, list) or not room_id:
        return []
    artwork_ids = {
        node.get("id")
        for node in nodes
        if isinstance(node, dict) and node.get("kind") == "artwork"
    }
    return [
        edge["source"]
        for edge in edges
        if isinstance(edge, dict)
        and edge.get("source") in artwork_ids
        and edge.get("target") == room_id
        and edge.get("relation") == "located_in"
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show a read-only live dashboard for the museum demo."
    )
    parser.add_argument(
        "--show-graph",
        action="store_true",
        help="show a compact active-session scene graph",
    )
    args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = DemoMonitor(args.show_graph)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.restore_terminal()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
