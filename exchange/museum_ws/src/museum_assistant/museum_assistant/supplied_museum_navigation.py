"""Pure helpers for deterministic supplied-museum route acceptance."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable

import yaml


DESTINATION_ROUTES = {
    "central_gallery": None,
    "north_gallery": "north_gallery",
    "south_west_gallery": "south_west_gallery",
    "south_east_gallery": "south_east_gallery",
}


@dataclass(frozen=True)
class Pose2D:
    """A named planar pose in the map frame."""

    name: str
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class TimedPose:
    """A planar pose with a ROS-clock timestamp expressed in nanoseconds."""

    stamp_ns: int
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class SynchronizedErrors:
    """Errors computed only from temporally matched pose sources."""

    stamp_ns: int
    corrected_gazebo_position: float
    corrected_gazebo_yaw: float
    localized_gazebo_position: float
    localized_gazebo_yaw: float


def normalize_angle(value: float) -> float:
    return math.atan2(math.sin(value), math.cos(value))


def position_error(
    first: TimedPose | Pose2D, second: TimedPose | Pose2D
) -> float:
    return math.hypot(first.x - second.x, first.y - second.y)


def yaw_error(first: TimedPose | Pose2D, second: TimedPose | Pose2D) -> float:
    return abs(normalize_angle(first.yaw - second.yaw))


def _read_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return value


def _pose(name: str, value: dict) -> Pose2D:
    if not isinstance(value, dict):
        raise ValueError(f"pose {name!r} must be a mapping")
    try:
        values = tuple(float(value[field]) for field in ("x", "y", "yaw"))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"pose {name!r} has invalid x, y, or yaw") from error
    if not all(math.isfinite(number) for number in values):
        raise ValueError(f"pose {name!r} contains a non-finite value")
    return Pose2D(name, *values)


def load_route_plan(
    destination: str,
    routes_path: Path,
    layout_path: Path,
) -> tuple[Pose2D, ...]:
    """Load one complete route and reject missing or duplicate waypoints."""

    if destination not in DESTINATION_ROUTES:
        raise ValueError(f"unknown supplied-museum destination: {destination}")
    routes = _read_yaml(routes_path)
    layout = _read_yaml(layout_path)
    route_nodes = routes.get("route_nodes")
    route_candidates = routes.get("candidate_poses")
    layout_candidates = layout.get("candidate_poses")
    route_definitions = routes.get("routes")
    if not all(
        isinstance(value, dict)
        for value in (
            route_nodes,
            route_candidates,
            layout_candidates,
            route_definitions,
        )
    ):
        raise ValueError("route and layout YAML mappings are incomplete")

    if destination == "central_gallery":
        names = ["candidate_central_gallery"]
    else:
        route_name = DESTINATION_ROUTES[destination]
        names = route_definitions.get(route_name)
        if not isinstance(names, list) or not names:
            raise ValueError(f"route {route_name!r} is missing or empty")

    if len(names) != len(set(names)):
        raise ValueError(
            f"route {destination!r} contains duplicate waypoint names"
        )

    waypoints = []
    for name in names:
        if not isinstance(name, str):
            raise ValueError(
                f"route {destination!r} contains a non-string waypoint"
            )
        if name in route_nodes:
            waypoint = _pose(name, route_nodes[name])
        elif name in route_candidates:
            waypoint = _pose(name, route_candidates[name])
            if name not in layout_candidates:
                raise ValueError(
                    f"candidate {name!r} is absent from the room layout"
                )
            layout_pose = _pose(name, layout_candidates[name])
            if waypoint != layout_pose:
                raise ValueError(
                    f"candidate {name!r} disagrees with the room layout"
                )
        elif name in layout_candidates:
            waypoint = _pose(name, layout_candidates[name])
        else:
            raise ValueError(f"unknown route waypoint: {name}")
        waypoints.append(waypoint)

    coordinates = [(pose.x, pose.y, pose.yaw) for pose in waypoints]
    if len(coordinates) != len(set(coordinates)):
        raise ValueError(
            f"route {destination!r} contains duplicate waypoint poses"
        )
    expected_final = {
        "central_gallery": "candidate_central_gallery",
        "north_gallery": "candidate_north",
        "south_west_gallery": "candidate_south_west",
        "south_east_gallery": "candidate_south_east",
    }[destination]
    if waypoints[-1].name != expected_final:
        raise ValueError(
            f"route {destination!r} ends at {waypoints[-1].name!r}, "
            f"not {expected_final!r}"
        )
    return tuple(waypoints)


def route_action_kind(waypoints: Iterable[Pose2D]) -> str:
    """Use one serialized NavigateToPose action for every route waypoint."""

    poses = tuple(waypoints)
    if not poses:
        raise ValueError("a route action requires at least one waypoint")
    return "navigate_to_pose"


class GoalSequence:
    """Serialize route goals and make duplicate dispatch impossible."""

    def __init__(self, waypoints: Iterable[Pose2D]):
        self.waypoints = tuple(waypoints)
        if not self.waypoints:
            raise ValueError("a goal sequence requires at least one waypoint")
        self.index = 0
        self.active: Pose2D | None = None
        self.state = "ready"

    def claim_next(self) -> Pose2D | None:
        if self.state in {"succeeded", "failed", "cancelled"}:
            return None
        if self.active is not None:
            raise RuntimeError("a route goal is already active")
        self.active = self.waypoints[self.index]
        self.state = "active"
        return self.active

    def finish_active(self, status: str) -> None:
        if self.active is None or self.state != "active":
            raise RuntimeError("there is no active route goal")
        self.active = None
        if status == "succeeded":
            self.index += 1
            self.state = (
                "succeeded" if self.index == len(self.waypoints) else "ready"
            )
        elif status == "cancelled":
            self.state = "cancelled"
        elif status == "failed":
            self.state = "failed"
        else:
            raise ValueError(f"unsupported goal result: {status}")

    def pause_active(self) -> None:
        if self.active is None or self.state != "active":
            raise RuntimeError("there is no active route goal to pause")
        self.state = "paused"

    def resume_active(self) -> Pose2D:
        if self.active is None or self.state != "paused":
            raise RuntimeError("there is no paused route goal to resume")
        self.state = "active"
        return self.active

    def cancel(self) -> None:
        if self.state not in {"succeeded", "failed", "cancelled"}:
            self.active = None
            self.state = "cancelled"


class LocalizationMonitor:
    """Evaluate synchronized TF without using AMCL topic cadence."""

    def __init__(
        self,
        max_skew_sec: float = 0.20,
        divergence_limit_m: float = 1.0,
        consecutive_limit: int = 5,
    ):
        if max_skew_sec <= 0.0 or divergence_limit_m <= 0.0:
            raise ValueError("monitor limits must be positive")
        if consecutive_limit < 1:
            raise ValueError("consecutive_limit must be positive")
        self.max_skew_ns = round(max_skew_sec * 1_000_000_000)
        self.divergence_limit_m = divergence_limit_m
        self.consecutive_limit = consecutive_limit
        self.consecutive_divergent = 0
        self.maximum_localized_error = 0.0
        self.maximum_corrected_error = 0.0
        self.last: SynchronizedErrors | None = None
        self.last_poses: tuple[TimedPose, TimedPose, TimedPose] | None = None

    def evaluate(
        self,
        gazebo: TimedPose,
        corrected: TimedPose,
        localized_tf: TimedPose | None,
    ) -> SynchronizedErrors | None:
        """Return errors only when all source times are sufficiently close."""

        if localized_tf is None:
            return None
        if (
            abs(gazebo.stamp_ns - corrected.stamp_ns) > self.max_skew_ns
            or abs(gazebo.stamp_ns - localized_tf.stamp_ns) > self.max_skew_ns
        ):
            return None
        errors = SynchronizedErrors(
            stamp_ns=gazebo.stamp_ns,
            corrected_gazebo_position=position_error(corrected, gazebo),
            corrected_gazebo_yaw=yaw_error(corrected, gazebo),
            localized_gazebo_position=position_error(localized_tf, gazebo),
            localized_gazebo_yaw=yaw_error(localized_tf, gazebo),
        )
        self.last = errors
        self.last_poses = (gazebo, corrected, localized_tf)
        self.maximum_corrected_error = max(
            self.maximum_corrected_error, errors.corrected_gazebo_position
        )
        self.maximum_localized_error = max(
            self.maximum_localized_error, errors.localized_gazebo_position
        )
        if errors.localized_gazebo_position > self.divergence_limit_m:
            self.consecutive_divergent += 1
        else:
            self.consecutive_divergent = 0
        return errors

    @property
    def cancellation_required(self) -> bool:
        return self.consecutive_divergent >= self.consecutive_limit


class TrinaryOccupancyMap:
    """Small standard-library PGM reader for physical route verification."""

    def __init__(self, yaml_path: Path):
        metadata = _read_yaml(yaml_path)
        self.resolution = float(metadata["resolution"])
        origin = metadata["origin"]
        self.origin_x, self.origin_y = float(origin[0]), float(origin[1])
        image_path = yaml_path.parent / metadata["image"]
        self.width, self.height, self.cells = self._read_pgm(image_path)

    @staticmethod
    def _read_pgm(path: Path) -> tuple[int, int, bytes]:
        data = path.read_bytes()
        if not data.startswith(b"P5"):
            raise ValueError(f"{path} must be a binary P5 PGM")
        index = 2

        def token() -> bytes:
            nonlocal index
            while index < len(data):
                if data[index:index + 1] == b"#":
                    newline = data.find(b"\n", index)
                    if newline < 0:
                        raise ValueError(f"unterminated PGM comment in {path}")
                    index = newline + 1
                elif data[index:index + 1].isspace():
                    index += 1
                else:
                    break
            start = index
            while index < len(data) and not data[index:index + 1].isspace():
                index += 1
            return data[start:index]

        width, height, maximum = (int(token()) for _ in range(3))
        if maximum != 255:
            raise ValueError(f"{path} must use 8-bit samples")
        while index < len(data) and data[index:index + 1].isspace():
            index += 1
        cells = data[index:]
        if len(cells) != width * height:
            raise ValueError(f"{path} has an unexpected raster size")
        return width, height, cells

    def value(self, x: float, y: float) -> int | None:
        column = math.floor((x - self.origin_x) / self.resolution)
        map_row = math.floor((y - self.origin_y) / self.resolution)
        if not (0 <= column < self.width and 0 <= map_row < self.height):
            return None
        image_row = self.height - 1 - map_row
        return self.cells[image_row * self.width + column]

    def is_known_free(self, x: float, y: float) -> bool:
        return self.value(x, y) == 254
