#!/usr/bin/env python3
"""Opt-in deterministic crowd motion for final-video Sketch 1 only."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import partial
import math
from pathlib import Path
from typing import Any

from ament_index_python.packages import get_package_share_directory
from gazebo_msgs.msg import EntityState, ModelStates
from gazebo_msgs.srv import SetEntityState, SpawnEntity
import rclpy
from rclpy.node import Node


UPDATE_HZ = 4.0
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
    bounds: tuple[float, float, float, float]
    speed: float
    spawn_pose: tuple[float, float, float] | None = None
    endpoint_a: tuple[float, float] = (0.0, 0.0)
    endpoint_b: tuple[float, float] = (0.0, 0.0)
    initial_direction: int = 1
    position: tuple[float, float] | None = None
    z: float = 0.0
    heading: float = 0.0
    target: tuple[float, float] | None = None
    last_update: float | None = None
    future: Any = None
    pending: tuple[
        tuple[float, float], float, tuple[float, float]
    ] | None = None
    invalid: bool = False


# Every segment stays inside the validated central-area free rectangle
# x=[-5.8, 5.8], y=[-18.0, 9.7]. Distinct lane heights and phase-shifted
# starting poses prevent the crowd from accumulating at shared waypoints.
WALKER_SPECS = (
    Walker(
        "visitor_marker",
        (-2.2, -0.8, -0.15, 0.15),
        0.18,
        endpoint_a=(-2.0, 0.0),
        endpoint_b=(-1.0, 0.0),
        initial_direction=-1,
    ),
    Walker(
        "guide_marker",
        (0.3, 4.5, 8.85, 9.15),
        0.23,
        endpoint_a=(0.4, 9.0),
        endpoint_b=(4.4, 9.0),
        initial_direction=1,
    ),
    Walker(
        "staff_marker",
        (0.2, 4.6, 3.7, 4.2),
        0.25,
        endpoint_a=(0.3, 3.8),
        endpoint_b=(4.5, 4.1),
        initial_direction=1,
    ),
    Walker(
        "guest_marker_1",
        (-0.3, 3.9, 2.85, 3.15),
        0.22,
        (1.30, 3.00, 0.0),
        (-0.2, 3.0),
        (3.8, 3.0),
        1,
    ),
    Walker(
        "guest_marker_2",
        (0.6, 4.8, 5.55, 6.05),
        0.20,
        (2.70, 5.80, -3.09),
        (0.7, 5.7),
        (4.7, 5.9),
        -1,
    ),
    Walker(
        "guest_marker_3",
        (0.9, 5.1, 7.15, 7.65),
        0.28,
        (3.40, 7.42, -3.09),
        (1.0, 7.3),
        (5.0, 7.5),
        -1,
    ),
)

if {walker.name for walker in WALKER_SPECS} != CROWD_MODEL_ALLOWLIST:
    raise RuntimeError("Crowd specifications must exactly match the safety allow-list")


class DemoCrowdMotion(Node):
    def __init__(self, seed: int, count: int) -> None:
        super().__init__("demo_crowd_motion")
        self.walkers = {
            template.name: _copy_walker(template) for template in WALKER_SPECS[:count]
        }
        mesh = (
            Path(get_package_share_directory("museum_assistant"))
            / "worlds/supplied_museum/humans/person_standing/meshes/standing.dae"
        )
        self.mesh_uri = mesh.as_uri()
        self.model_names: set[str] = set()
        self.received_models = False
        self.started = False
        self.spawn_requested: set[str] = set()
        self.spawn_future = None
        self.spawn_name: str | None = None
        self.service_warning = False

        self.set_client = self.create_client(
            SetEntityState, "/gazebo/set_entity_state"
        )
        self.spawn_client = self.create_client(SpawnEntity, "/spawn_entity")
        self.create_subscription(
            ModelStates, "/gazebo/model_states", self._models, 10
        )
        self.create_timer(1.0 / UPDATE_HZ, self._update)
        self.get_logger().info(
            f"Sketch 1 fixed-lane crowd requested: count={count}, "
            f"compatibility_seed={seed}, "
            f"update_rate={UPDATE_HZ:.1f} Hz"
        )
        self.get_logger().info(
            "SetEntityState allow-list: "
            + ", ".join(sorted(CROWD_MODEL_ALLOWLIST))
        )

    def _models(self, message: ModelStates) -> None:
        poses = dict(zip(message.name, message.pose))
        self.model_names = set(poses)
        self.received_models = True
        now = self._now()
        for walker in self.walkers.values():
            pose = poses.get(walker.name)
            if pose is None or walker.invalid:
                continue
            values = (
                pose.position.x,
                pose.position.y,
                pose.position.z,
                pose.orientation.x,
                pose.orientation.y,
                pose.orientation.z,
                pose.orientation.w,
            )
            if not all(math.isfinite(value) for value in values):
                continue
            if not _inside(walker.bounds, pose.position.x, pose.position.y, 0.3):
                walker.invalid = True
                self.get_logger().error(
                    f"Refusing to move {walker.name}: pose is outside its "
                    "validated social-navigation corridor"
                )
                continue
            walker.position = (pose.position.x, pose.position.y)
            walker.z = pose.position.z
            walker.heading = _yaw(pose.orientation)
            if walker.last_update is None:
                walker.last_update = now

        if not self.started and all(
            walker.position is not None and not walker.invalid
            for walker in self.walkers.values()
        ):
            for walker in self.walkers.values():
                walker.target = (
                    walker.endpoint_b
                    if walker.initial_direction > 0
                    else walker.endpoint_a
                )
                walker.last_update = now
            self.started = True
            self.get_logger().info(
                "All requested pedestrians are present; fixed-lane motion started"
            )

    def _update(self) -> None:
        if not self.received_models:
            return
        self._spawn_missing_guest()
        if not self.started:
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
        for walker in self.walkers.values():
            if walker.future is not None or walker.last_update is None:
                continue
            dt = min(max(now - walker.last_update, 0.0), 0.5)
            if dt <= 0.0:
                continue
            position, heading, velocity, target = self._step(walker, dt)
            request = _state_request(walker, position, heading, velocity)
            walker.pending = (position, heading, target)
            walker.last_update = now
            walker.future = self.set_client.call_async(request)
            walker.future.add_done_callback(
                partial(self._movement_result, walker.name)
            )

    def _spawn_missing_guest(self) -> None:
        if self.spawn_future is not None:
            return
        missing = [
            walker
            for walker in self.walkers.values()
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

    def _step(
        self, walker: Walker, dt: float
    ) -> tuple[
        tuple[float, float],
        float,
        tuple[float, float],
        tuple[float, float],
    ]:
        position = walker.position
        target = walker.target
        remaining = walker.speed * dt
        heading = walker.heading

        # Consume any small remainder after reaching an endpoint so motion is
        # continuous. Reversal changes yaw by approximately pi, never position.
        for _ in range(2):
            distance = _distance(position, target)
            if distance > remaining:
                heading = math.atan2(
                    target[1] - position[1], target[0] - position[0]
                )
                ratio = remaining / distance
                position = (
                    position[0] + (target[0] - position[0]) * ratio,
                    position[1] + (target[1] - position[1]) * ratio,
                )
                remaining = 0.0
                break

            position = target
            remaining -= distance
            target = (
                walker.endpoint_b
                if target == walker.endpoint_a
                else walker.endpoint_a
            )

        heading = math.atan2(
            target[1] - position[1], target[0] - position[0]
        )
        velocity = (
            walker.speed * math.cos(heading),
            walker.speed * math.sin(heading),
        )
        return position, heading, velocity, target

    def _movement_result(self, name: str, future) -> None:
        walker = self.walkers[name]
        pending = walker.pending
        walker.future = None
        walker.pending = None
        try:
            response = future.result()
        except Exception as error:
            self.get_logger().warning(f"Failed to move {name}: {error}")
            return
        if response is None or not response.success:
            self.get_logger().warning(f"Gazebo rejected movement for {name}")
            return
        if pending is not None:
            walker.position, walker.heading, walker.target = pending

    def _now(self) -> float:
        return self.get_clock().now().nanoseconds / 1.0e9


def _state_request(
    walker: Walker,
    position: tuple[float, float],
    heading: float,
    velocity: tuple[float, float],
):
    if walker.name not in CROWD_MODEL_ALLOWLIST:
        raise ValueError(f"Refusing SetEntityState for non-crowd model {walker.name!r}")
    request = SetEntityState.Request()
    state = EntityState()
    state.name = walker.name
    state.reference_frame = "world"
    state.pose.position.x, state.pose.position.y = position
    state.pose.position.z = walker.z
    state.pose.orientation.z = math.sin(heading / 2.0)
    state.pose.orientation.w = math.cos(heading / 2.0)
    state.twist.linear.x, state.twist.linear.y = velocity
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


def _inside(
    bounds: tuple[float, float, float, float],
    x: float,
    y: float,
    tolerance: float = 0.0,
) -> bool:
    x_min, x_max, y_min, y_max = bounds
    return (
        x_min - tolerance <= x <= x_max + tolerance
        and y_min - tolerance <= y <= y_max + tolerance
    )


def _copy_walker(template: Walker) -> Walker:
    return Walker(
        template.name,
        template.bounds,
        template.speed,
        template.spawn_pose,
        template.endpoint_a,
        template.endpoint_b,
        template.initial_direction,
    )


def _yaw(quaternion) -> float:
    return math.atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0 - 2.0 * (quaternion.y**2 + quaternion.z**2),
    )


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


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
