#!/usr/bin/env python3
"""Deterministic six-person walking choreography for final-video Sketch 1."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from ament_index_python.packages import get_package_share_directory
from gazebo_msgs.msg import EntityState, ModelStates
from gazebo_msgs.srv import SetEntityState, SpawnEntity
import rclpy
from rclpy.node import Node


UPDATE_HZ = 5.0
CROWD_MODEL_ALLOWLIST = frozenset(
    {
        "visitor_marker",
        "guide_marker",
        "staff_marker",
        "guest_marker_1",
        "guest_marker_2",
        "guest_marker_3",
    }
)
GUEST_MODELS = frozenset(
    {"guest_marker_1", "guest_marker_2", "guest_marker_3"}
)


@dataclass
class Walker:
    name: str
    public_id: str
    endpoint_a: tuple[float, float]
    endpoint_b: tuple[float, float]
    speed: float
    phase_fraction: float
    spawn_pose: tuple[float, float, float] | None = None
    z: float = 0.0
    future: Any = None

    @property
    def length(self) -> float:
        return math.hypot(
            self.endpoint_b[0] - self.endpoint_a[0],
            self.endpoint_b[1] - self.endpoint_a[1],
        )

    @property
    def period(self) -> float:
        return 2.0 * self.length / self.speed


# Video 1 now deliberately uses the validated north-gallery target (0, 16).
# All six pedestrians walk continuously INSIDE the north room (y > 10):
# three cross the robot's centerline x ~= 0 at different depths, while three
# remain on lateral paths.  This makes the encounter obvious on video without
# allowing all six people to collapse into the same point.
#
# The supplied navigation proxy has the north-room entrance at y=10 with a
# clear x=-3..3 opening; the paths below remain in the open x=-5..5 interior.
WALKER_SPECS = (
    Walker(
        "visitor_marker",
        "visitor_1",
        (-4.8, 11.8),
        (-2.8, 17.5),
        0.20,
        0.08,
    ),
    Walker(
        "guest_marker_1",
        "guest_1",
        (-2.8, 11.8),
        (2.8, 12.2),
        0.24,
        0.34,
        (-1.0, 12.0, 0.07),
    ),
    Walker(
        "staff_marker",
        "staff_1",
        (4.5, 11.8),
        (3.3, 18.0),
        0.22,
        0.56,
    ),
    Walker(
        "guest_marker_2",
        "guest_2",
        (2.8, 13.3),
        (-2.8, 14.6),
        0.27,
        0.77,
        (1.2, 13.7, 2.91),
    ),
    Walker(
        "guide_marker",
        "guide_1",
        (-4.7, 14.2),
        (-2.6, 19.0),
        0.25,
        0.91,
    ),
    Walker(
        "guest_marker_3",
        "guest_3",
        (-2.8, 14.8),
        (2.8, 15.3),
        0.30,
        0.63,
        (0.8, 15.1, 0.09),
    ),
)

if {walker.name for walker in WALKER_SPECS} != CROWD_MODEL_ALLOWLIST:
    raise RuntimeError("Crowd specifications must exactly match the safety allow-list")


class DemoCrowdMotion(Node):
    def __init__(self, seed: int, count: int) -> None:
        super().__init__("demo_crowd_motion")
        self.walkers = list(WALKER_SPECS[:count])
        mesh = (
            Path(get_package_share_directory("museum_assistant"))
            / "worlds/supplied_museum/humans/person_standing/meshes/standing.dae"
        )
        self.mesh_uri = mesh.as_uri()
        self.model_names: set[str] = set()
        self.received_models = False
        self.started = False
        self.start_time: float | None = None
        self.spawn_requested: set[str] = set()
        self.spawn_future = None
        self.spawn_name: str | None = None
        self.service_warning = False

        self.set_client = self.create_client(
            SetEntityState, "/gazebo/set_entity_state"
        )
        self.spawn_client = self.create_client(SpawnEntity, "/spawn_entity")
        self.create_subscription(ModelStates, "/gazebo/model_states", self._models, 10)
        self.create_timer(1.0 / UPDATE_HZ, self._update)

        self.get_logger().info(
            f"Sketch 1 north-gallery crowd: count={count}, "
            f"compatibility_seed={seed}, update_rate={UPDATE_HZ:.1f} Hz"
        )
        self.get_logger().info(
            "SetEntityState allow-list: "
            + ", ".join(sorted(CROWD_MODEL_ALLOWLIST))
        )
        for walker in self.walkers:
            ax, ay = walker.endpoint_a
            bx, by = walker.endpoint_b
            crosses_route = min(ax, bx) <= 0.0 <= max(ax, bx)
            self.get_logger().info(
                f"{walker.public_id}: ({ax:.1f},{ay:.1f}) <-> "
                f"({bx:.1f},{by:.1f}), {walker.speed:.2f} m/s, "
                f"{'CROSSING' if crosses_route else 'LATERAL'}"
            )

    def _models(self, message: ModelStates) -> None:
        poses = dict(zip(message.name, message.pose))
        self.model_names = set(poses)
        self.received_models = True
        for walker in self.walkers:
            pose = poses.get(walker.name)
            if pose is not None and math.isfinite(pose.position.z):
                walker.z = pose.position.z

    def _update(self) -> None:
        if not self.received_models:
            return

        self._spawn_missing_guest()
        if not all(walker.name in self.model_names for walker in self.walkers):
            return

        if not self.set_client.service_is_ready():
            if not self.service_warning:
                self.get_logger().warning("Waiting for /gazebo/set_entity_state")
                self.service_warning = True
            return

        if self.service_warning:
            self.get_logger().info("Gazebo SetEntityState service is ready")
            self.service_warning = False

        now = self._now()
        if not self.started:
            self.start_time = now
            self.started = True
            self.get_logger().info(
                "All six pedestrians present; north-gallery walking started"
            )

        elapsed = max(now - self.start_time, 0.0)
        for walker in self.walkers:
            if walker.future is not None:
                if not walker.future.done():
                    continue
                try:
                    response = walker.future.result()
                except Exception as error:
                    self.get_logger().warning(f"Failed to move {walker.name}: {error}")
                else:
                    if response is None or not response.success:
                        self.get_logger().warning(
                            f"Gazebo rejected movement for {walker.name}"
                        )
                walker.future = None

            x, y, heading, vx, vy = _analytical_pose(walker, elapsed)
            walker.future = self.set_client.call_async(
                _state_request(walker, x, y, heading, vx, vy)
            )

    def _spawn_missing_guest(self) -> None:
        if self.spawn_future is not None:
            return

        missing = [
            walker
            for walker in self.walkers
            if walker.name in GUEST_MODELS
            and walker.name not in self.model_names
            and walker.name not in self.spawn_requested
        ]
        if not missing or not self.spawn_client.service_is_ready():
            return

        walker = missing[0]
        request = SpawnEntity.Request()
        request.name = walker.name
        request.xml = _guest_sdf(walker.name, self.mesh_uri)
        x, y, yaw = walker.spawn_pose
        request.initial_pose.position.x = x
        request.initial_pose.position.y = y
        request.initial_pose.orientation.z = math.sin(yaw / 2.0)
        request.initial_pose.orientation.w = math.cos(yaw / 2.0)
        request.reference_frame = "world"

        self.spawn_name = walker.name
        self.spawn_requested.add(walker.name)
        self.spawn_future = self.spawn_client.call_async(request)
        self.spawn_future.add_done_callback(self._spawn_result)

    def _spawn_result(self, future) -> None:
        name = self.spawn_name
        self.spawn_future = None
        self.spawn_name = None
        try:
            response = future.result()
        except Exception as error:
            response = None
            self.get_logger().warning(f"Failed to spawn {name}: {error}")

        if response is None or not response.success:
            self.spawn_requested.discard(name)
            if response is not None:
                self.get_logger().warning(
                    f"Gazebo rejected spawn for {name}: {response.status_message}"
                )
            return

        self.get_logger().info(f"Spawned demo-only pedestrian {name}")

    def _now(self) -> float:
        return self.get_clock().now().nanoseconds / 1.0e9


def _analytical_pose(
    walker: Walker, elapsed: float
) -> tuple[float, float, float, float, float]:
    """Return pose and velocity from a triangle wave along one line segment."""
    ax, ay = walker.endpoint_a
    bx, by = walker.endpoint_b
    dx = bx - ax
    dy = by - ay
    length = walker.length
    ux = dx / length
    uy = dy / length

    phase_time = (elapsed + walker.phase_fraction * walker.period) % walker.period
    one_way_time = length / walker.speed

    if phase_time < one_way_time:
        distance = walker.speed * phase_time
        x = ax + ux * distance
        y = ay + uy * distance
        heading = math.atan2(uy, ux)
        return x, y, heading, walker.speed * ux, walker.speed * uy

    distance = walker.speed * (phase_time - one_way_time)
    x = bx - ux * distance
    y = by - uy * distance
    heading = math.atan2(-uy, -ux)
    return x, y, heading, -walker.speed * ux, -walker.speed * uy


def _state_request(
    walker: Walker,
    x: float,
    y: float,
    heading: float,
    vx: float,
    vy: float,
):
    if walker.name not in CROWD_MODEL_ALLOWLIST:
        raise ValueError(f"Refusing SetEntityState for non-crowd model {walker.name!r}")

    request = SetEntityState.Request()
    state = EntityState()
    state.name = walker.name
    state.reference_frame = "world"
    state.pose.position.x = x
    state.pose.position.y = y
    state.pose.position.z = walker.z
    state.pose.orientation.z = math.sin(heading / 2.0)
    state.pose.orientation.w = math.cos(heading / 2.0)
    state.twist.linear.x = vx
    state.twist.linear.y = vy
    request.state = state
    return request


def _guest_sdf(name: str, mesh_uri: str) -> str:
    if name not in GUEST_MODELS:
        raise ValueError(f"Refusing to spawn non-guest model {name!r}")
    return f"""<?xml version="1.0"?>
<sdf version="1.6">
  <model name="{name}">
    <static>true</static>
    <link name="body">
      <visual name="human">
        <geometry><mesh><uri>{mesh_uri}</uri></mesh></geometry>
      </visual>
      <collision name="body_collision">
        <pose>0 0 0.45 0 0 0</pose>
        <geometry><cylinder><radius>0.16</radius><length>0.75</length></cylinder></geometry>
      </collision>
    </link>
  </model>
</sdf>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, choices=range(1, 7), default=6)
    arguments, ros_arguments = parser.parse_known_args()

    rclpy.init(args=ros_arguments)
    node = DemoCrowdMotion(arguments.seed, arguments.count)
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
