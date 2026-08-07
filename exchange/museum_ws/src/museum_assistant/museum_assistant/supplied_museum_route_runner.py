"""Execute and verify one supplied-museum route using normal Nav2 actions."""

from __future__ import annotations

import argparse
from collections import deque
import json
import math
from pathlib import Path
import signal
import sys
from threading import Event
import time

from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from gazebo_msgs.msg import ModelStates
from geometry_msgs.msg import PoseStamped, TwistStamped
from nav2_msgs.action import NavigateThroughPoses, NavigateToPose
from nav_msgs.msg import Odometry, Path as NavPath
import rclpy
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from rclpy.time import Time
from rclpy.utilities import remove_ros_args
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from tf2_ros import Buffer, TransformException, TransformListener

from .escort import EscortState, EscortSupervisor
from .supplied_museum_navigation import (
    DESTINATION_ROUTES,
    GoalSequence,
    LocalizationMonitor,
    Pose2D,
    TimedPose,
    TrinaryOccupancyMap,
    load_route_plan,
    position_error,
)


CANCEL_REQUESTED = Event()


def _yaw(quaternion) -> float:
    return math.atan2(
        2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
        1.0
        - 2.0 * (quaternion.y * quaternion.y + quaternion.z * quaternion.z),
    )


def _stamp_ns(stamp) -> int:
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def _pose_dict(pose: TimedPose | None) -> dict | None:
    if pose is None:
        return None
    return {
        "stamp_ns": pose.stamp_ns,
        "x": pose.x,
        "y": pose.y,
        "yaw": pose.yaw,
    }


class SuppliedMuseumRouteRunner(Node):
    """Monitor three pose sources while serializing goals."""

    def __init__(
        self,
        occupancy_map: TrinaryOccupancyMap,
        route_request: dict | None = None,
    ):
        super().__init__("supplied_museum_route_runner")
        self.occupancy_map = occupancy_map
        self.route_request = route_request
        self.client = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self.route_client = ActionClient(
            self, NavigateThroughPoses, "navigate_through_poses"
        )
        self.tf_buffer = Buffer(cache_time=Duration(seconds=30.0))
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.monitor = LocalizationMonitor()
        self.gazebo_samples: deque[TimedPose] = deque(maxlen=1000)
        self.corrected_samples: deque[TimedPose] = deque(maxlen=1000)
        self.original_samples: deque[TimedPose] = deque(maxlen=1000)
        self.localized_samples: deque[TimedPose] = deque(maxlen=1000)
        self.pending_scan_stamps: deque[int] = deque(maxlen=100)
        self.latest_scan_stamp_ns: int | None = None
        self.last_tf_sample_stamp_ns: int | None = None
        self.scan_count = 0
        self.plan_count = 0
        self.cmd_count = 0
        self.nonzero_cmd_count = 0
        self.latest_cmd = (0.0, 0.0)
        self.latest_cmd_stamp_ns = 0
        self.physical_distance_m = 0.0
        self._distance_pose: TimedPose | None = None
        self._distance_sample_ns = 0
        self.map_violation_count = 0
        self.first_map_violation: dict | None = None
        self.goal_uuids: list[str] = []
        self.active_goal_handle = None
        self.active_waypoint: str | None = None
        self.action_state = "idle"
        self.samples: list[dict] = []
        self._next_sample_ns: int | None = None
        self.active_route_targets: tuple[Pose2D, ...] = ()
        self.minimum_route_distances: dict[str, float] = {}
        self.remaining_poses: int | None = None
        self.escort: EscortSupervisor | None = None
        self.escort_state_history: list[dict] = []
        self._escort_cancel_reason: str | None = None

        self.create_subscription(
            ModelStates, "/gazebo/model_states", self._gazebo, 10
        )
        self.create_subscription(
            Odometry, "/museum/ground_truth_odom", self._corrected, 20
        )
        self.create_subscription(
            Odometry, "/mobile_base_controller/odom", self._original, 20
        )
        self.create_subscription(
            LaserScan, "/scan_raw", self._scan, qos_profile_sensor_data
        )
        self.create_subscription(NavPath, "/plan", self._plan, 10)
        self.create_subscription(
            TwistStamped,
            "/mobile_base_controller/cmd_vel_out",
            self._command,
            20,
        )
        if route_request is not None:
            escort_defaults = {
                "resume_distance": 2.0,
                "wait_distance": 3.0,
                "lost_distance": 8.0,
                "arrival_distance": 2.5,
                "wait_delay": 3.0,
                "absence_timeout": 3.0,
            }
            for name, value in escort_defaults.items():
                self.declare_parameter(name, value)
            self.escort = EscortSupervisor(
                **{
                    name: float(self.get_parameter(name).value)
                    for name in escort_defaults
                }
            )
            self.escort_publisher = self.create_publisher(
                String, "/museum/escort_state", 10
            )
            self.create_subscription(
                String,
                "/museum/visitor_observation",
                self._handle_visitor_observation,
                10,
            )

    @property
    def gazebo(self) -> TimedPose | None:
        return self.gazebo_samples[-1] if self.gazebo_samples else None

    @property
    def corrected(self) -> TimedPose | None:
        return self.corrected_samples[-1] if self.corrected_samples else None

    @property
    def original(self) -> TimedPose | None:
        return self.original_samples[-1] if self.original_samples else None

    @property
    def localized(self) -> TimedPose | None:
        return self.localized_samples[-1] if self.localized_samples else None

    def _gazebo(self, message: ModelStates) -> None:
        names = [
            index for index, name in enumerate(message.name) if "tiago" in name
        ]
        if len(names) != 1:
            return
        pose = message.pose[names[0]]
        stamp_ns = self.get_clock().now().nanoseconds
        sample = TimedPose(
            stamp_ns, pose.position.x, pose.position.y, _yaw(pose.orientation)
        )
        self.gazebo_samples.append(sample)

    @staticmethod
    def _odom_pose(message: Odometry) -> TimedPose:
        pose = message.pose.pose
        return TimedPose(
            _stamp_ns(message.header.stamp),
            pose.position.x,
            pose.position.y,
            _yaw(pose.orientation),
        )

    def _corrected(self, message: Odometry) -> None:
        self.corrected_samples.append(self._odom_pose(message))

    def _original(self, message: Odometry) -> None:
        self.original_samples.append(self._odom_pose(message))

    def _scan(self, message: LaserScan) -> None:
        self.scan_count += 1
        self.latest_scan_stamp_ns = _stamp_ns(message.header.stamp)
        self.pending_scan_stamps.append(self.latest_scan_stamp_ns)

    def _plan(self, _message: NavPath) -> None:
        self.plan_count += 1

    def _command(self, message: TwistStamped) -> None:
        self.cmd_count += 1
        self.latest_cmd = (message.twist.linear.x, message.twist.angular.z)
        self.latest_cmd_stamp_ns = _stamp_ns(message.header.stamp)
        if (
            abs(self.latest_cmd[0]) > 1.0e-3
            or abs(self.latest_cmd[1]) > 1.0e-3
        ):
            self.nonzero_cmd_count += 1

    def start_escort(self) -> None:
        if self.escort is not None:
            self.escort.start()
            self._publish_escort_state()

    def _handle_visitor_observation(self, message: String) -> None:
        if self.escort is None or self.route_request is None:
            return
        try:
            observation = json.loads(message.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warning(
                f"Ignoring malformed visitor-observation JSON: {exc}"
            )
            return
        if not isinstance(observation, dict):
            return
        if observation.get("session_id") != self.route_request.get(
            "session_id"
        ):
            return

        previous = self.escort.state
        try:
            current = self.escort.observe(
                present=observation.get("present"),
                distance_to_robot=observation.get("distance_to_robot"),
                now=self.get_clock().now().nanoseconds / 1e9,
            )
        except ValueError as exc:
            self.get_logger().warning(
                f"Ignoring invalid visitor observation: {exc}"
            )
            return
        self._publish_escort_state()
        if current is previous:
            return

        if (
            current is EscortState.WAITING
            and not self.escort.navigation_reached_destination
        ):
            self._escort_cancel_reason = "escort_wait"
        elif current is EscortState.LOST:
            self._escort_cancel_reason = "escort_lost"
        self.get_logger().info(f"Escort state changed to {current.value}")

    def _publish_escort_state(self) -> None:
        if (
            self.escort is None
            or self.escort.state is None
            or self.route_request is None
        ):
            return
        payload = {
            field: self.route_request.get(field)
            for field in ("request_id", "session_id", "selected_room")
        }
        payload["state"] = self.escort.state.value
        if self.escort.distance_to_robot is not None:
            payload["distance_to_robot"] = self.escort.distance_to_robot
        if (
            not self.escort_state_history
            or self.escort_state_history[-1]["state"] != payload["state"]
        ):
            self.escort_state_history.append(dict(payload))
        message = String()
        message.data = json.dumps(payload)
        self.escort_publisher.publish(message)

    def wait_for_escort_resume(self) -> bool:
        if self.escort is None:
            return True
        while rclpy.ok() and self.escort.state is EscortState.WAITING:
            self.spin_sample()
        return self.escort.state is EscortState.ESCORTING

    def finish_escort_navigation(self) -> None:
        if self.escort is None:
            return
        previous = self.escort.state
        current = self.escort.navigation_succeeded()
        self._publish_escort_state()
        if current is not previous and current is not None:
            self.get_logger().info(
                f"Escort state changed to {current.value}"
            )
        while rclpy.ok() and self.escort.state is EscortState.WAITING:
            self.spin_sample()

    @staticmethod
    def _closest(
        samples: deque[TimedPose], stamp_ns: int, maximum_skew_ns: int
    ) -> TimedPose | None:
        if not samples:
            return None
        candidate = min(
            samples, key=lambda value: abs(value.stamp_ns - stamp_ns)
        )
        if abs(candidate.stamp_ns - stamp_ns) > maximum_skew_ns:
            return None
        return candidate

    def sample_synchronized_localization(self) -> None:
        if not self.pending_scan_stamps:
            return
        stamp_ns = self.pending_scan_stamps[0]
        age_ns = self.get_clock().now().nanoseconds - stamp_ns
        if age_ns < 150_000_000:
            return
        try:
            transform = self.tf_buffer.lookup_transform(
                "map",
                "base_footprint",
                Time(nanoseconds=stamp_ns),
                timeout=Duration(seconds=0.03),
            )
        except TransformException:
            if age_ns > 2_000_000_000:
                self.pending_scan_stamps.popleft()
            return
        self.pending_scan_stamps.popleft()
        self.last_tf_sample_stamp_ns = stamp_ns
        translation = transform.transform.translation
        localized = TimedPose(
            stamp_ns,
            translation.x,
            translation.y,
            _yaw(transform.transform.rotation),
        )
        self.localized_samples.append(localized)
        gazebo = self._closest(
            self.gazebo_samples, stamp_ns, self.monitor.max_skew_ns
        )
        corrected = self._closest(
            self.corrected_samples, stamp_ns, self.monitor.max_skew_ns
        )
        if gazebo is not None and corrected is not None:
            self.monitor.evaluate(gazebo, corrected, localized)

    def sample_physical_route(self) -> None:
        sample = self.gazebo
        if (
            sample is None
            or sample.stamp_ns - self._distance_sample_ns < 100_000_000
        ):
            return
        self._distance_sample_ns = sample.stamp_ns
        if self._distance_pose is not None:
            self.physical_distance_m += position_error(
                sample, self._distance_pose
            )
        self._distance_pose = sample
        if not self.occupancy_map.is_known_free(sample.x, sample.y):
            self.map_violation_count += 1
            if self.first_map_violation is None:
                self.first_map_violation = _pose_dict(sample)
        for target in self.active_route_targets:
            distance = position_error(sample, target)
            self.minimum_route_distances[target.name] = min(
                distance,
                self.minimum_route_distances.get(target.name, math.inf),
            )

    def spin_sample(self, timeout_sec: float = 0.05) -> None:
        rclpy.spin_once(self, timeout_sec=timeout_sec)
        self.sample_synchronized_localization()
        self.sample_physical_route()
        self.sample_report()

    def sample_report(self) -> None:
        now_ns = self.get_clock().now().nanoseconds
        if now_ns <= 0:
            return
        if self._next_sample_ns is None:
            self._next_sample_ns = now_ns
        if now_ns < self._next_sample_ns:
            return
        self._next_sample_ns = now_ns + 5_000_000_000
        self.samples.append(
            {
                "stamp_ns": now_ns,
                "waypoint": self.active_waypoint,
                "action_state": self.action_state,
                "gazebo_pose": _pose_dict(self.gazebo),
                "corrected_odom_pose": _pose_dict(self.corrected),
                "localized_tf_pose": _pose_dict(self.localized),
                "cmd_linear_x": self.latest_cmd[0],
                "cmd_angular_z": self.latest_cmd[1],
                "synchronized_localization_error_m": (
                    None
                    if self.monitor.last is None
                    else self.monitor.last.localized_gazebo_position
                ),
            }
        )

    def wait_until_ready(self, timeout_sec: float = 90.0) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            self.spin_sample()
            if (
                self.client.server_is_ready()
                and self.route_client.server_is_ready()
                and self.scan_count > 0
                and self.gazebo is not None
                and self.corrected is not None
                and self.monitor.last is not None
                and self.get_clock().now().nanoseconds > 0
            ):
                return self.monitor.last.corrected_gazebo_position <= 0.10
        return False

    def readiness(self) -> dict:
        return {
            "action_server": self.client.server_is_ready(),
            "route_action_server": self.route_client.server_is_ready(),
            "scan_count": self.scan_count,
            "gazebo_pose": _pose_dict(self.gazebo),
            "corrected_odom_pose": _pose_dict(self.corrected),
            "localized_tf_pose": _pose_dict(self.localized),
            "synchronized_errors": (
                None
                if self.monitor.last is None
                else {
                    "stamp_ns": self.monitor.last.stamp_ns,
                    "corrected_gazebo_position": (
                        self.monitor.last.corrected_gazebo_position
                    ),
                    "localized_gazebo_position": (
                        self.monitor.last.localized_gazebo_position
                    ),
                }
            ),
            "pending_scan_stamps": len(self.pending_scan_stamps),
            "clock_ns": self.get_clock().now().nanoseconds,
        }

    def _wait_future(self, future, timeout_sec: float):
        deadline = time.monotonic() + timeout_sec
        while not future.done() and time.monotonic() < deadline:
            self.spin_sample()
        return future.result() if future.done() else None

    def cancel_goal(self, goal_handle) -> bool:
        future = goal_handle.cancel_goal_async()
        response = self._wait_future(future, 10.0)
        return response is not None and bool(response.goals_canceling)

    def wait_for_zero_command(
        self, after_stamp_ns: int, timeout_sec: float = 5.0
    ) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            self.spin_sample()
            if (
                self.latest_cmd_stamp_ns >= after_stamp_ns
                and abs(self.latest_cmd[0]) <= 1.0e-3
                and abs(self.latest_cmd[1]) <= 1.0e-3
            ):
                return True
        return False

    def wait_for_synchronized_localization(
        self, after_stamp_ns: int, timeout_sec: float = 10.0
    ) -> bool:
        """Wait for synchronized poses newer than an action result."""

        self.pending_scan_stamps.clear()
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            self.spin_sample()
            poses = self.monitor.last_poses
            if poses is not None and poses[2].stamp_ns >= after_stamp_ns:
                return True
        return False

    def execute_waypoint(
        self,
        waypoint: Pose2D,
        timeout_sim_sec: float,
        behavior_tree: Path,
    ) -> dict:
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = waypoint.x
        goal.pose.pose.position.y = waypoint.y
        goal.pose.pose.orientation.z = math.sin(waypoint.yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(waypoint.yaw / 2.0)
        goal.behavior_tree = str(behavior_tree)
        plan_count_before = self.plan_count
        nonzero_before = self.nonzero_cmd_count
        start_sim_ns = self.get_clock().now().nanoseconds
        start_wall = time.monotonic()
        send_future = self.client.send_goal_async(goal)
        self.active_waypoint = waypoint.name
        self.action_state = "requesting"
        goal_handle = self._wait_future(send_future, 15.0)
        if goal_handle is None or not goal_handle.accepted:
            self.action_state = "rejected"
            return {"name": waypoint.name, "status": "rejected"}

        uuid = bytes(goal_handle.goal_id.uuid).hex()
        self.goal_uuids.append(uuid)
        self.active_goal_handle = goal_handle
        self.action_state = "active"
        result_future = goal_handle.get_result_async()
        cancellation_reason = None
        wall_deadline = start_wall + max(300.0, timeout_sim_sec * 3.0)
        while not result_future.done():
            self.spin_sample()
            elapsed_sim = (
                self.get_clock().now().nanoseconds - start_sim_ns
            ) / 1.0e9
            if self._escort_cancel_reason is not None:
                cancellation_reason = self._escort_cancel_reason
            elif self.monitor.cancellation_required:
                cancellation_reason = "localization_divergence"
            elif CANCEL_REQUESTED.is_set():
                cancellation_reason = "external_cancel"
            elif elapsed_sim > timeout_sim_sec:
                cancellation_reason = "simulation_timeout"
            elif time.monotonic() > wall_deadline:
                cancellation_reason = "wall_timeout"
            if cancellation_reason is not None:
                self.cancel_goal(goal_handle)
                break

        result = self._wait_future(result_future, 15.0)
        self.active_goal_handle = None
        status_code = (
            result.status if result is not None else GoalStatus.STATUS_UNKNOWN
        )
        end_sim_ns = self.get_clock().now().nanoseconds
        fresh_localization = self.wait_for_synchronized_localization(
            end_sim_ns
        )
        zero_command = self.wait_for_zero_command(end_sim_ns)
        status_name = {
            GoalStatus.STATUS_SUCCEEDED: "succeeded",
            GoalStatus.STATUS_ABORTED: "failed",
            GoalStatus.STATUS_CANCELED: "cancelled",
        }.get(status_code, "failed")
        if cancellation_reason is not None:
            status_name = "cancelled"
        if cancellation_reason == self._escort_cancel_reason:
            self._escort_cancel_reason = None
        self.action_state = status_name
        self.active_waypoint = None
        return {
            "name": waypoint.name,
            "target": {"x": waypoint.x, "y": waypoint.y, "yaw": waypoint.yaw},
            "uuid": uuid,
            "accepted": True,
            "status": status_name,
            "nav2_status_code": status_code,
            "cancellation_reason": cancellation_reason,
            "duration_sim_sec": (end_sim_ns - start_sim_ns) / 1.0e9,
            "duration_wall_sec": time.monotonic() - start_wall,
            "global_path_produced": self.plan_count > plan_count_before,
            "nonzero_command_produced": (
                self.nonzero_cmd_count > nonzero_before
            ),
            "terminal_command_zero": zero_command,
            "fresh_localization_tf": fresh_localization,
            "gazebo_pose": _pose_dict(self.gazebo),
            "corrected_odom_pose": _pose_dict(self.corrected),
            "localized_tf_pose": _pose_dict(self.localized),
        }

    @staticmethod
    def _stamped_pose(node: Node, waypoint: Pose2D) -> PoseStamped:
        pose = PoseStamped()
        pose.header.frame_id = "map"
        pose.header.stamp = node.get_clock().now().to_msg()
        pose.pose.position.x = waypoint.x
        pose.pose.position.y = waypoint.y
        pose.pose.orientation.z = math.sin(waypoint.yaw / 2.0)
        pose.pose.orientation.w = math.cos(waypoint.yaw / 2.0)
        return pose

    def _route_feedback(self, message) -> None:
        self.remaining_poses = int(message.feedback.number_of_poses_remaining)

    def execute_route(
        self,
        waypoints: tuple[Pose2D, ...],
        timeout_sim_sec: float,
        behavior_tree: Path,
    ) -> dict:
        """Send an entire topological route as exactly one Nav2 action."""

        goal = NavigateThroughPoses.Goal()
        goal.poses = [self._stamped_pose(self, pose) for pose in waypoints]
        goal.behavior_tree = str(behavior_tree)
        plan_count_before = self.plan_count
        nonzero_before = self.nonzero_cmd_count
        start_sim_ns = self.get_clock().now().nanoseconds
        start_wall = time.monotonic()
        self.active_route_targets = waypoints
        self.minimum_route_distances = {
            waypoint.name: math.inf for waypoint in waypoints
        }
        self.remaining_poses = len(waypoints)
        self.active_waypoint = "navigate_through_poses"
        self.action_state = "requesting"
        send_future = self.route_client.send_goal_async(
            goal, feedback_callback=self._route_feedback
        )
        goal_handle = self._wait_future(send_future, 15.0)
        if goal_handle is None or not goal_handle.accepted:
            self.action_state = "rejected"
            self.active_route_targets = ()
            return {"name": "navigate_through_poses", "status": "rejected"}

        uuid = bytes(goal_handle.goal_id.uuid).hex()
        self.goal_uuids.append(uuid)
        self.active_goal_handle = goal_handle
        self.action_state = "active"
        result_future = goal_handle.get_result_async()
        cancellation_reason = None
        wall_deadline = start_wall + max(1200.0, timeout_sim_sec * 3.0)
        while not result_future.done():
            self.spin_sample()
            elapsed_sim = (
                self.get_clock().now().nanoseconds - start_sim_ns
            ) / 1.0e9
            if self.monitor.cancellation_required:
                cancellation_reason = "localization_divergence"
            elif CANCEL_REQUESTED.is_set():
                cancellation_reason = "external_cancel"
            elif elapsed_sim > timeout_sim_sec:
                cancellation_reason = "simulation_timeout"
            elif time.monotonic() > wall_deadline:
                cancellation_reason = "wall_timeout"
            if cancellation_reason is not None:
                self.cancel_goal(goal_handle)
                break

        result = self._wait_future(result_future, 15.0)
        self.active_goal_handle = None
        status_code = (
            result.status if result is not None else GoalStatus.STATUS_UNKNOWN
        )
        end_sim_ns = self.get_clock().now().nanoseconds
        fresh_localization = self.wait_for_synchronized_localization(
            end_sim_ns
        )
        zero_command = self.wait_for_zero_command(end_sim_ns)
        status_name = {
            GoalStatus.STATUS_SUCCEEDED: "succeeded",
            GoalStatus.STATUS_ABORTED: "failed",
            GoalStatus.STATUS_CANCELED: "cancelled",
        }.get(status_code, "failed")
        if cancellation_reason is not None:
            status_name = "cancelled"
        minimum_distances = dict(self.minimum_route_distances)
        self.active_route_targets = ()
        self.action_state = status_name
        self.active_waypoint = None
        completed = [
            waypoint.name
            for waypoint in waypoints
            if minimum_distances[waypoint.name] <= 0.75
        ]
        if status_name == "succeeded":
            completed = [waypoint.name for waypoint in waypoints]
        return {
            "name": "navigate_through_poses",
            "waypoint_names": [waypoint.name for waypoint in waypoints],
            "completed_waypoints": completed,
            "minimum_waypoint_distances_m": minimum_distances,
            "uuid": uuid,
            "accepted": True,
            "status": status_name,
            "nav2_status_code": status_code,
            "cancellation_reason": cancellation_reason,
            "duration_sim_sec": (end_sim_ns - start_sim_ns) / 1.0e9,
            "duration_wall_sec": time.monotonic() - start_wall,
            "global_path_produced": self.plan_count > plan_count_before,
            "nonzero_command_produced": (
                self.nonzero_cmd_count > nonzero_before
            ),
            "terminal_command_zero": zero_command,
            "fresh_localization_tf": fresh_localization,
            "remaining_poses_feedback": self.remaining_poses,
            "gazebo_pose": _pose_dict(self.gazebo),
            "corrected_odom_pose": _pose_dict(self.corrected),
            "localized_tf_pose": _pose_dict(self.localized),
        }


def _final_metrics(node: SuppliedMuseumRouteRunner, target: Pose2D) -> dict:
    synchronized = node.monitor.last_poses
    if synchronized is None:
        gazebo, corrected, localized = None, None, None
    else:
        gazebo, corrected, localized = synchronized
    original = node.original
    return {
        "target": {
            "name": target.name,
            "x": target.x,
            "y": target.y,
            "yaw": target.yaw,
        },
        "gazebo_pose": _pose_dict(gazebo),
        "corrected_odom_pose": _pose_dict(corrected),
        "localized_tf_pose": _pose_dict(localized),
        "original_controller_odom_pose": _pose_dict(original),
        "gazebo_target_error_m": (
            position_error(gazebo, target) if gazebo else None
        ),
        "corrected_target_error_m": (
            position_error(corrected, target) if corrected else None
        ),
        "localized_target_error_m": (
            position_error(localized, target) if localized else None
        ),
        "corrected_gazebo_error_m": position_error(corrected, gazebo)
        if corrected and gazebo else None,
        "original_gazebo_error_m": position_error(original, gazebo)
        if original and gazebo else None,
        "maximum_corrected_gazebo_error_m": (
            node.monitor.maximum_corrected_error
        ),
        "maximum_localized_gazebo_error_m": (
            node.monitor.maximum_localized_error
        ),
        "physical_distance_m": node.physical_distance_m,
        "scan_count": node.scan_count,
        "map_violation_count": node.map_violation_count,
        "first_map_violation": node.first_map_violation,
    }


def terminal_localization_is_fresh(waypoint_results: list[dict]) -> bool:
    """Require fresh synchronized localization at the completed route target."""

    return bool(waypoint_results) and bool(
        waypoint_results[-1].get("fresh_localization_tf", False)
    )


def correlated_navigation_result(
    route_request: dict, final_candidate: str, report: dict
) -> dict:
    """Build a terminal result whose success is tied to the final candidate."""

    final = report.get("final")
    if not isinstance(final, dict):
        final = {}
    target = final.get("target")
    if not isinstance(target, dict):
        target = {}
    target_error = final.get("gazebo_target_error_m")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        checks = {}
    candidate_reached = (
        target.get("name") == final_candidate
        and isinstance(target_error, (int, float))
        and not isinstance(target_error, bool)
        and math.isfinite(float(target_error))
        and float(target_error) <= 0.50
    )
    nav2_succeeded = checks.get("all_nav2_goals_succeeded") is True
    succeeded = candidate_reached and nav2_succeeded
    navigation_events = []
    for waypoint in report.get("waypoints", []):
        if waypoint.get("accepted") is True:
            event = {
                "status": "accepted",
                "waypoint": waypoint.get("name"),
                "goal_uuid": waypoint.get("uuid"),
            }
            navigation_events.append(event)
        cancellation_reason = waypoint.get("cancellation_reason")
        terminal_status = waypoint.get("status")
        if cancellation_reason == "escort_wait":
            terminal_status = "intentionally_canceled_for_escort_wait"
        elif cancellation_reason == "escort_lost":
            terminal_status = "canceled_for_escort_lost"
        navigation_events.append(
            {
                "status": terminal_status,
                "waypoint": waypoint.get("name"),
                "goal_uuid": waypoint.get("uuid"),
            }
        )
    result_status = "succeeded" if succeeded else "failed"
    if report.get("status") == "cancelled":
        result_status = "canceled"
    return {
        "request_id": route_request.get("request_id"),
        "session_id": route_request.get("session_id"),
        "selected_room": route_request.get("selected_room"),
        "route": route_request.get("route"),
        "final_candidate": final_candidate,
        "status": result_status,
        "candidate_reached": candidate_reached,
        "nav2_succeeded": nav2_succeeded,
        "gazebo_target_error_m": target_error,
        "nav2_goal_count": len(report.get("goal_uuids", [])),
        "goal_uuids": list(report.get("goal_uuids", [])),
        "navigation_events": navigation_events,
        "escort_states": list(report.get("escort_states", [])),
        "runner_status": report.get("status", "failed"),
        "reason": (
            "final_candidate_reached"
            if succeeded
            else report.get("reason", "final_candidate_not_reached")
        ),
    }


class SuppliedMuseumRouteRequestBridge(Node):
    """Queue validated route requests and publish correlated final results."""

    def __init__(self, routes_path: Path, layout_path: Path):
        super().__init__("supplied_museum_route_request_bridge")
        self.routes_path = routes_path
        self.layout_path = layout_path
        self.pending: deque[tuple[dict, str]] = deque()
        self.seen_correlations: set[tuple[object, object]] = set()
        self.result_publisher = self.create_publisher(
            String, "/museum/navigation_result", 10
        )
        self.create_subscription(
            String,
            "/museum/supplied_route_request",
            self._receive_request,
            10,
        )
        self.get_logger().info(
            "Waiting for one-shot route requests on "
            "/museum/supplied_route_request"
        )

    def _receive_request(self, message: String) -> None:
        try:
            request = json.loads(message.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warning(
                f"Rejecting malformed supplied-route request: {exc}"
            )
            return
        if not isinstance(request, dict):
            self.get_logger().warning(
                "Rejecting supplied-route request that is not an object"
            )
            return

        correlation = (request.get("session_id"), request.get("request_id"))
        if correlation in self.seen_correlations:
            self._publish_rejection(request, "duplicate_route_request")
            return
        route = request.get("route")
        if not isinstance(route, str):
            self._publish_rejection(request, "unknown_route")
            return
        try:
            waypoints = load_route_plan(
                route, self.routes_path, self.layout_path
            )
        except (OSError, ValueError) as exc:
            self._publish_rejection(request, f"unknown_route: {exc}")
            return
        self.seen_correlations.add(correlation)
        self.pending.append((request, waypoints[-1].name))
        self.get_logger().info(
            "Accepted correlated route request: "
            f"request_id={request.get('request_id')} route={route}"
        )

    def pop_request(self) -> tuple[dict, str] | None:
        return self.pending.popleft() if self.pending else None

    def publish_result(self, result: dict) -> None:
        message = String()
        message.data = json.dumps(result)
        self.result_publisher.publish(message)
        self.get_logger().info(
            "Published correlated terminal navigation result: "
            f"request_id={result.get('request_id')} "
            f"status={result.get('status')}"
        )

    def _publish_rejection(self, request: dict, reason: str) -> None:
        self.publish_result(
            {
                "request_id": request.get("request_id"),
                "session_id": request.get("session_id"),
                "selected_room": request.get("selected_room"),
                "route": request.get("route"),
                "final_candidate": None,
                "status": "rejected",
                "candidate_reached": False,
                "nav2_succeeded": False,
                "gazebo_target_error_m": None,
                "nav2_goal_count": 0,
                "runner_status": "rejected",
                "reason": reason,
            }
        )


def run(args, route_request: dict | None = None) -> tuple[int, dict]:
    waypoints = load_route_plan(args.destination, args.routes, args.layout)
    occupancy_map = TrinaryOccupancyMap(args.map)
    sequence = GoalSequence(waypoints)
    node = SuppliedMuseumRouteRunner(occupancy_map, route_request)
    report = {
        "destination": args.destination,
        "route": [pose.name for pose in waypoints],
        "waypoints": [],
        "goal_uuids": node.goal_uuids,
        "samples": node.samples,
        "escort_states": node.escort_state_history,
    }
    try:
        if not node.wait_until_ready():
            report.update(
                {
                    "status": "failed",
                    "reason": "runtime_not_ready",
                    "readiness": node.readiness(),
                }
            )
            return 2, report
        initial = _final_metrics(node, waypoints[-1])
        report["initial"] = initial
        report["initial_localization_ready_via_tf"] = True
        node.start_escort()
        while sequence.state not in {"succeeded", "failed", "cancelled"}:
            if node.escort is not None and node.escort.state is EscortState.LOST:
                sequence.cancel()
                break
            waypoint = sequence.claim_next()
            is_final = sequence.index == len(waypoints) - 1
            timeout = (
                args.final_timeout if is_final else args.intermediate_timeout
            )
            while sequence.state == "active":
                result = node.execute_waypoint(
                    waypoint, timeout, args.waypoint_behavior_tree
                )
                report["waypoints"].append(result)
                if result.get("status") == "succeeded":
                    sequence.finish_active("succeeded")
                elif result.get("cancellation_reason") == "escort_wait":
                    sequence.pause_active()
                    if not node.wait_for_escort_resume():
                        sequence.cancel()
                        break
                    waypoint = sequence.resume_active()
                elif result.get("status") == "cancelled":
                    sequence.finish_active("cancelled")
                else:
                    sequence.finish_active("failed")
        route_state = sequence.state
        if route_state == "succeeded":
            node.finish_escort_navigation()

        final = _final_metrics(node, waypoints[-1])
        report["final"] = final
        physical_waypoints_passed = True
        if len(waypoints) > 1:
            successful_results = [
                result
                for result in report["waypoints"]
                if result.get("status") == "succeeded"
            ]
            physical_waypoints_passed = all(
                result.get("gazebo_pose") is not None
                and math.hypot(
                    result["gazebo_pose"]["x"] - waypoint.x,
                    result["gazebo_pose"]["y"] - waypoint.y,
                ) <= 0.50
                for result, waypoint in zip(successful_results, waypoints)
            )
        checks = {
            "all_nav2_goals_succeeded": route_state == "succeeded",
            "unique_goal_uuid_per_attempt": (
                len(node.goal_uuids) == len(report["waypoints"])
                and len(node.goal_uuids) == len(set(node.goal_uuids))
            ),
            "global_path_each_waypoint": all(
                value.get("global_path_produced", False)
                for value in report["waypoints"]
            ),
            "physical_motion": final["physical_distance_m"] > 0.05,
            "physical_route_waypoints": physical_waypoints_passed,
            "gazebo_target_error": final["gazebo_target_error_m"] is not None
            and final["gazebo_target_error_m"] <= 0.50,
            "localized_target_error": (
                final["localized_target_error_m"] is not None
                and final["localized_target_error_m"] <= 0.50
            ),
            "corrected_gazebo_consistency": (
                final["corrected_gazebo_error_m"] is not None
                and final["corrected_gazebo_error_m"] <= 0.10
            ),
            "localized_gazebo_consistency": (
                final["maximum_localized_gazebo_error_m"] <= 1.0
            ),
            "known_free_physical_route": final["map_violation_count"] == 0,
            "terminal_command_zero": all(
                value.get("terminal_command_zero", False)
                for value in report["waypoints"]
            ),
            "fresh_localization_tf": terminal_localization_is_fresh(
                report["waypoints"]
            ),
        }
        report["checks"] = checks
        if (
            route_state == "cancelled"
            and node.escort is not None
            and node.escort.state is EscortState.LOST
        ):
            report["status"] = "cancelled"
            report["reason"] = "escort_lost"
        else:
            report["status"] = "passed" if all(checks.values()) else "failed"
        return (0 if report["status"] == "passed" else 3), report
    except KeyboardInterrupt:
        if node.active_goal_handle is not None:
            node.cancel_goal(node.active_goal_handle)
            node.wait_for_zero_command(node.get_clock().now().nanoseconds)
        sequence.cancel()
        report.update({"status": "cancelled", "reason": "keyboard_interrupt"})
        return 130, report
    finally:
        node.destroy_node()


def parse_args(argv=None):
    share = Path(get_package_share_directory("museum_assistant"))
    parser = argparse.ArgumentParser(
        description=(
            "Execute one synchronized supplied-museum Nav2 route acceptance"
        )
    )
    parser.add_argument(
        "--destination", choices=tuple(DESTINATION_ROUTES), required=True
    )
    parser.add_argument(
        "--routes",
        type=Path,
        default=share / "config/supplied_museum_routes.yaml",
    )
    parser.add_argument(
        "--layout",
        type=Path,
        default=share / "config/supplied_museum_room_layout.yaml",
    )
    parser.add_argument(
        "--map", type=Path, default=share / "maps/supplied_museum_nav.yaml"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--intermediate-timeout", type=float, default=240.0)
    parser.add_argument("--final-timeout", type=float, default=300.0)
    parser.add_argument(
        "--waypoint-behavior-tree",
        type=Path,
        default=share / "behavior_trees/supplied_museum_to_pose.xml",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    raw_args = sys.argv if argv is None else [sys.argv[0], *argv]
    args = parse_args(remove_ros_args(raw_args)[1:])
    CANCEL_REQUESTED.clear()

    def request_cancel(_signum, _frame):
        CANCEL_REQUESTED.set()

    signal.signal(signal.SIGINT, request_cancel)
    signal.signal(signal.SIGTERM, request_cancel)
    rclpy.init(
        args=raw_args, signal_handler_options=SignalHandlerOptions.NO
    )
    try:
        exit_code, report = run(args)
    finally:
        if rclpy.ok():
            rclpy.shutdown()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    sys.exit(exit_code)


def topic_main(args=None) -> None:
    """Run the supplied route runner behind its correlated ROS topic API."""

    share = Path(get_package_share_directory("museum_assistant"))
    routes_path = share / "config/supplied_museum_routes.yaml"
    layout_path = share / "config/supplied_museum_room_layout.yaml"
    bridge = None
    CANCEL_REQUESTED.clear()
    rclpy.init(args=args)
    try:
        bridge = SuppliedMuseumRouteRequestBridge(routes_path, layout_path)
        while rclpy.ok():
            rclpy.spin_once(bridge, timeout_sec=0.10)
            pending = bridge.pop_request()
            if pending is None:
                continue
            request, final_candidate = pending
            run_args = argparse.Namespace(
                destination=request["route"],
                routes=routes_path,
                layout=layout_path,
                map=share / "maps/supplied_museum_nav.yaml",
                intermediate_timeout=240.0,
                final_timeout=300.0,
                waypoint_behavior_tree=(
                    share / "behavior_trees/supplied_museum_to_pose.xml"
                ),
            )
            try:
                _exit_code, report = run(run_args, route_request=request)
            except Exception as exc:
                bridge.get_logger().error(
                    f"Supplied-museum route execution failed: {exc}"
                )
                report = {"status": "failed", "reason": str(exc)}
            bridge.publish_result(
                correlated_navigation_result(request, final_candidate, report)
            )
    except KeyboardInterrupt:
        pass
    finally:
        if bridge is not None:
            bridge.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
