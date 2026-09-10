#!/usr/bin/env python3
"""Place Video 1 pedestrians, with an optional slowly moving guide."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from ament_index_python.packages import get_package_share_directory
from gazebo_msgs.msg import EntityState, ModelStates
from gazebo_msgs.srv import DeleteEntity, SetEntityState, SpawnEntity
import rclpy
from rclpy.node import Node


@dataclass(frozen=True)
class StaticPerson:
    model_name: str
    public_id: str
    x: float
    y: float
    yaw: float
    guest: bool = False
    group: str = ""


# There is intentionally NO waypoint route in Video 1. TIAGo receives only
# north_gallery (0,16). The central groups stay well outside the x=0 corridor;
# guide_1 uses the accepted benchmark geometry to create one controlled social
# influence near the north-gallery opening without physically blocking it.
#
# visitor_marker is explicitly deleted from Gazebo for this video because the
# supplied world spawns it at (-1,0), visually next to TIAGo. Ten people are
# still shown by using guest_marker_1..8 plus staff_marker and guide_marker.
PEOPLE = (
    # Three-person group on the left side of the central room.
    StaticPerson("guest_marker_1", "guest_1", -5.0, 5.0, 0.20, True, "LEFT"),
    StaticPerson("guest_marker_2", "guest_2", -4.4, 7.0, 0.0, True, "LEFT"),
    StaticPerson("guest_marker_3", "guest_3", -5.6, 8.4, -0.20, True, "LEFT"),
    # Three-person group on the right side of the central room.
    StaticPerson("staff_marker", "staff_1", 4.7, 4.5, math.pi, False, "RIGHT"),
    StaticPerson("guest_marker_4", "guest_4", 5.3, 6.5, math.pi, True, "RIGHT"),
    StaticPerson("guest_marker_5", "guest_5", 4.5, 8.4, 2.90, True, "RIGHT"),
    # The sole route-relevant person, lateral to the nominal x=0 path.
    StaticPerson("guide_marker", "guide_1", 1.2, 9.0, math.pi, False, "GUIDE"),
    # Three visitors spread laterally inside the north gallery.
    StaticPerson("guest_marker_6", "guest_6", -5.0, 13.0, 0.35, True, "NORTH"),
    StaticPerson("guest_marker_7", "guest_7", 5.0, 13.5, 2.80, True, "NORTH"),
    StaticPerson("guest_marker_8", "guest_8", -4.5, 17.0, 0.15, True, "NORTH"),
)

ALLOWLIST = frozenset(person.model_name for person in PEOPLE)
GUESTS = frozenset(person.model_name for person in PEOPLE if person.guest)
REMOVED_NEAR_SPAWN_MODEL = "visitor_marker"
GUIDE_MODEL = "guide_marker"
GUIDE_MOTION_X = 1.4
GUIDE_MOTION_MIN_Y = 8.2
GUIDE_MOTION_MAX_Y = 9.2
GUIDE_MOTION_INITIAL_Y = 9.0
GUIDE_MOTION_SPEED = 0.12

if len(PEOPLE) != 10 or len(ALLOWLIST) != 10:
    raise RuntimeError("Video 1 static demo must contain exactly ten unique people")


class StaticPeopleDemo(Node):
    def __init__(self, move_guide: bool = False) -> None:
        super().__init__("demo_static_people")
        self.move_guide = move_guide
        mesh = (
            Path(get_package_share_directory("museum_assistant"))
            / "worlds/supplied_museum/humans/person_standing/meshes/standing.dae"
        )
        self.mesh_uri = mesh.as_uri()
        self.model_names: set[str] = set()
        self.z_by_name: dict[str, float] = {}
        self.placed: set[str] = set()
        self.pending_set: dict[str, Any] = {}
        self.spawn_requested: set[str] = set()
        self.spawn_future = None
        self.spawn_name: str | None = None
        self.delete_future = None
        self.delete_requested = False
        self.reported_ready = False
        self.guide_motion_start = None
        self.guide_motion_future = None

        self.set_client = self.create_client(SetEntityState, "/gazebo/set_entity_state")
        self.spawn_client = self.create_client(SpawnEntity, "/spawn_entity")
        self.delete_client = self.create_client(DeleteEntity, "/delete_entity")
        self.create_subscription(ModelStates, "/gazebo/model_states", self._models, 10)
        self.create_timer(0.25, self._tick)

        mode = "9 static people + moving guide" if move_guide else "10 static people"
        self.get_logger().info(f"Video 1: {mode}, one single north-gallery goal")
        for person in PEOPLE:
            x, y, yaw = self._initial_pose(person)
            self.get_logger().info(
                f"  group {person.group} | {person.public_id}: "
                f"({x:.1f}, {y:.1f}) yaw={math.degrees(yaw):.0f} deg"
            )
        if move_guide:
            self.get_logger().info(
                "  guide_1 motion: x=1.4, y=8.2..9.2, speed=0.12 m/s"
            )

    def _models(self, msg: ModelStates) -> None:
        self.model_names = set(msg.name)
        for name, pose in zip(msg.name, msg.pose):
            if name in ALLOWLIST and math.isfinite(pose.position.z):
                self.z_by_name[name] = pose.position.z

    def _tick(self) -> None:
        self._remove_near_spawn_visitor()
        self._finish_pending_sets()
        self._spawn_missing_guest()

        if not self.set_client.service_is_ready():
            return
        if REMOVED_NEAR_SPAWN_MODEL in self.model_names:
            return
        if not all(person.model_name in self.model_names for person in PEOPLE):
            return

        for person in PEOPLE:
            if (
                person.model_name in self.placed
                or person.model_name in self.pending_set
            ):
                continue
            x, y, yaw = self._initial_pose(person)
            request = SetEntityState.Request()
            state = EntityState()
            state.name = person.model_name
            state.reference_frame = "world"
            state.pose.position.x = x
            state.pose.position.y = y
            state.pose.position.z = self.z_by_name.get(person.model_name, 0.0)
            state.pose.orientation.z = math.sin(yaw / 2.0)
            state.pose.orientation.w = math.cos(yaw / 2.0)
            request.state = state
            self.pending_set[person.model_name] = self.set_client.call_async(request)

        if len(self.placed) == len(PEOPLE) and not self.reported_ready:
            self.reported_ready = True
            if self.move_guide:
                self.guide_motion_start = self.get_clock().now()
                self.get_logger().info(
                    "MOVING-GUIDE PEOPLE READY: 10 people placed; "
                    "9 static and guide_1 moving"
                )
            else:
                self.get_logger().info(
                    "STATIC PEOPLE READY: 10 people placed; "
                    "near-spawn visitor removed"
                )

        if self.reported_ready and self.move_guide:
            self._move_guide()

    def _initial_pose(self, person: StaticPerson) -> tuple[float, float, float]:
        if self.move_guide and person.model_name == GUIDE_MODEL:
            return GUIDE_MOTION_X, GUIDE_MOTION_INITIAL_Y, math.pi / 2.0
        return person.x, person.y, person.yaw

    def _move_guide(self) -> None:
        if GUIDE_MODEL not in ALLOWLIST:
            raise RuntimeError(
                "Refusing to move a model outside the Video 1 allow-list"
            )
        if self.guide_motion_future is not None:
            if not self.guide_motion_future.done():
                return
            try:
                response = self.guide_motion_future.result()
            except Exception as exc:
                self.get_logger().error(f"Guide motion update failed: {exc}")
            else:
                if response is None or not response.success:
                    self.get_logger().error("Gazebo rejected guide motion update")
            self.guide_motion_future = None

        if self.guide_motion_start is None:
            return
        elapsed = (
            self.get_clock().now() - self.guide_motion_start
        ).nanoseconds / 1e9
        y, direction = _guide_motion(elapsed)
        yaw = math.pi / 2.0 if direction > 0.0 else -math.pi / 2.0

        request = SetEntityState.Request()
        state = EntityState()
        state.name = GUIDE_MODEL
        state.reference_frame = "world"
        state.pose.position.x = GUIDE_MOTION_X
        state.pose.position.y = y
        state.pose.position.z = self.z_by_name.get(GUIDE_MODEL, 0.0)
        state.pose.orientation.z = math.sin(yaw / 2.0)
        state.pose.orientation.w = math.cos(yaw / 2.0)
        state.twist.linear.y = direction * GUIDE_MOTION_SPEED
        request.state = state
        self.guide_motion_future = self.set_client.call_async(request)

    def _remove_near_spawn_visitor(self) -> None:
        if REMOVED_NEAR_SPAWN_MODEL not in self.model_names:
            return
        if self.delete_future is not None:
            if not self.delete_future.done():
                return
            try:
                response = self.delete_future.result()
            except Exception as exc:
                self.get_logger().error(f"Failed to remove visitor_marker: {exc}")
                self.delete_future = None
                self.delete_requested = False
                return
            if response is not None and response.success:
                self.get_logger().info("Removed visitor_marker next to TIAGo spawn")
            else:
                self.get_logger().error("Gazebo rejected visitor_marker deletion")
                self.delete_requested = False
            self.delete_future = None
            return
        if self.delete_requested or not self.delete_client.service_is_ready():
            return
        request = DeleteEntity.Request()
        request.name = REMOVED_NEAR_SPAWN_MODEL
        self.delete_requested = True
        self.delete_future = self.delete_client.call_async(request)

    def _finish_pending_sets(self) -> None:
        for name, future in list(self.pending_set.items()):
            if not future.done():
                continue
            del self.pending_set[name]
            try:
                response = future.result()
            except Exception as exc:
                self.get_logger().error(f"SetEntityState failed for {name}: {exc}")
                continue
            if response is not None and response.success:
                self.placed.add(name)
            else:
                self.get_logger().error(f"Gazebo rejected static placement for {name}")

    def _spawn_missing_guest(self) -> None:
        if self.spawn_future is not None or not self.spawn_client.service_is_ready():
            return
        missing = [
            person
            for person in PEOPLE
            if person.guest
            and person.model_name not in self.model_names
            and person.model_name not in self.spawn_requested
        ]
        if not missing:
            return

        person = missing[0]
        request = SpawnEntity.Request()
        request.name = person.model_name
        request.xml = _guest_sdf(person.model_name, self.mesh_uri)
        request.initial_pose.position.x = person.x
        request.initial_pose.position.y = person.y
        request.initial_pose.orientation.z = math.sin(person.yaw / 2.0)
        request.initial_pose.orientation.w = math.cos(person.yaw / 2.0)
        request.reference_frame = "world"

        self.spawn_requested.add(person.model_name)
        self.spawn_name = person.model_name
        self.spawn_future = self.spawn_client.call_async(request)
        self.spawn_future.add_done_callback(self._spawn_done)

    def _spawn_done(self, future) -> None:
        name = self.spawn_name
        self.spawn_future = None
        self.spawn_name = None
        try:
            response = future.result()
        except Exception as exc:
            self.spawn_requested.discard(name)
            self.get_logger().error(f"Spawn failed for {name}: {exc}")
            return
        if response is None or not response.success:
            self.spawn_requested.discard(name)
            message = response.status_message if response is not None else "no response"
            self.get_logger().error(f"Gazebo rejected spawn for {name}: {message}")
        else:
            self.get_logger().info(f"Spawned {name}")


def _guest_sdf(name: str, mesh_uri: str) -> str:
    if name not in GUESTS:
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


def _guide_motion(elapsed: float) -> tuple[float, float]:
    """Return analytic triangle-wave y and direction for simulation time."""
    span = GUIDE_MOTION_MAX_Y - GUIDE_MOTION_MIN_Y
    initial_offset = GUIDE_MOTION_INITIAL_Y - GUIDE_MOTION_MIN_Y
    distance = (initial_offset + GUIDE_MOTION_SPEED * max(0.0, elapsed)) % (
        2.0 * span
    )
    if distance < span:
        return GUIDE_MOTION_MIN_Y + distance, 1.0
    return GUIDE_MOTION_MAX_Y - (distance - span), -1.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Place the ten Video 1 people in Gazebo."
    )
    parser.add_argument(
        "--move-guide",
        action="store_true",
        help="move only guide_1 along the bounded Video 1 lateral lane",
    )
    arguments, ros_arguments = parser.parse_known_args()
    rclpy.init(args=ros_arguments)
    node = StaticPeopleDemo(move_guide=arguments.move_guide)
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
