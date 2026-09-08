#!/usr/bin/env python3
"""Place ten stationary pedestrians for the single-goal Video 1 demo."""

from __future__ import annotations

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
# north_gallery (0,16). The first group lies on the nominal straight route,
# but far enough from spawn that the robot visibly drives straight first and
# only later reshapes its trajectory under the local social critic.
#
# visitor_marker is explicitly deleted from Gazebo for this video because the
# supplied world spawns it at (-1,0), visually next to TIAGo. Ten people are
# still shown by using guest_marker_1..8 plus staff_marker and guide_marker.
PEOPLE = (
    # Group A: directly ahead, around six metres from the start.
    StaticPerson("guest_marker_1", "guest_1", -0.75, 5.8, 0.20, True, "A"),
    StaticPerson("guest_marker_2", "guest_2", 0.35, 6.1, math.pi, True, "A"),
    StaticPerson("guest_marker_3", "guest_3", 1.35, 5.7, 2.80, True, "A"),
    # Group B: farther ahead and biased right, leaving a feasible local detour.
    StaticPerson("staff_marker", "staff_1", 1.0, 8.0, 0.0, False, "B"),
    StaticPerson("guest_marker_4", "guest_4", 2.0, 8.3, math.pi, True, "B"),
    StaticPerson("guest_marker_5", "guest_5", 2.8, 8.6, 2.60, True, "B"),
    # Group C: north room population, away from the final goal.
    StaticPerson("guide_marker", "guide_1", -4.0, 12.8, 0.35, False, "C"),
    StaticPerson("guest_marker_6", "guest_6", -3.0, 13.8, 2.90, True, "C"),
    StaticPerson("guest_marker_7", "guest_7", 3.4, 12.9, math.pi, True, "C"),
    StaticPerson("guest_marker_8", "guest_8", 4.0, 14.2, 2.65, True, "C"),
)

ALLOWLIST = frozenset(person.model_name for person in PEOPLE)
GUESTS = frozenset(person.model_name for person in PEOPLE if person.guest)
REMOVED_NEAR_SPAWN_MODEL = "visitor_marker"

if len(PEOPLE) != 10 or len(ALLOWLIST) != 10:
    raise RuntimeError("Video 1 static demo must contain exactly ten unique people")


class StaticPeopleDemo(Node):
    def __init__(self) -> None:
        super().__init__("demo_static_people")
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

        self.set_client = self.create_client(SetEntityState, "/gazebo/set_entity_state")
        self.spawn_client = self.create_client(SpawnEntity, "/spawn_entity")
        self.delete_client = self.create_client(DeleteEntity, "/delete_entity")
        self.create_subscription(ModelStates, "/gazebo/model_states", self._models, 10)
        self.create_timer(0.25, self._tick)

        self.get_logger().info("Video 1: 10 static people, one single north-gallery goal")
        for person in PEOPLE:
            self.get_logger().info(
                f"  group {person.group} | {person.public_id}: "
                f"({person.x:.1f}, {person.y:.1f}) yaw={math.degrees(person.yaw):.0f} deg"
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
            if person.model_name in self.placed or person.model_name in self.pending_set:
                continue
            request = SetEntityState.Request()
            state = EntityState()
            state.name = person.model_name
            state.reference_frame = "world"
            state.pose.position.x = person.x
            state.pose.position.y = person.y
            state.pose.position.z = self.z_by_name.get(person.model_name, 0.0)
            state.pose.orientation.z = math.sin(person.yaw / 2.0)
            state.pose.orientation.w = math.cos(person.yaw / 2.0)
            request.state = state
            self.pending_set[person.model_name] = self.set_client.call_async(request)

        if len(self.placed) == len(PEOPLE) and not self.reported_ready:
            self.reported_ready = True
            self.get_logger().info(
                "STATIC PEOPLE READY: 10 people placed; near-spawn visitor removed"
            )

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


def main() -> None:
    rclpy.init()
    node = StaticPeopleDemo()
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
