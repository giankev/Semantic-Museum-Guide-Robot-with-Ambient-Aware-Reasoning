#!/usr/bin/env python3
"""Record and compare supplied-museum baseline/social-force episodes."""

import argparse
import json
import math
from pathlib import Path
import time

from action_msgs.msg import GoalStatus, GoalStatusArray
from gazebo_msgs.msg import ModelStates
from geometry_msgs.msg import TwistStamped
from nav2_msgs.action import NavigateToPose
import rclpy
from rcl_interfaces.msg import Log
from rclpy.node import Node
from rclpy.parameter import Parameter
from social_nav_msgs.msg import Pedestrians
from std_msgs.msg import String


EXPECTED_ESCORT = ["escorting", "waiting", "escorting", "arrived"]


class ComparisonProbe(Node):
    def __init__(self, request_id: str, person_id: str, person_model: str):
        super().__init__(
            "supplied_social_force_comparison_probe",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        self.request_id = request_id
        self.person_id = person_id
        self.person_model = person_model
        self.decision = None
        self.route_requests = []
        self.escort_states = []
        self.navigation_result = None
        self.people_messages = 0
        self.people_identifiers = set()
        self.navigation_start_sim = None
        self.navigation_start_wall = None
        self.navigation_end_sim = None
        self.navigation_end_wall = None
        self.physical_path_length = 0.0
        self.minimum_person_distance = math.inf
        self.initial_person_pose = None
        self._previous_robot_position = None
        self._finished = False
        self.maximum_recoveries = 0
        self.no_progress_failures = 0
        self.latest_command = (math.inf, math.inf)

        self.request_publisher = self.create_publisher(
            String, "/museum/user_request", 10
        )
        self.create_subscription(
            String, "/museum/assistant_response", self._decision, 10
        )
        self.create_subscription(
            String, "/museum/supplied_route_request", self._route, 10
        )
        self.create_subscription(
            String, "/museum/escort_state", self._escort, 10
        )
        self.create_subscription(
            String, "/museum/navigation_result", self._result, 10
        )
        self.create_subscription(
            ModelStates, "/gazebo/model_states", self._models, 10
        )
        self.create_subscription(Pedestrians, "/people", self._people, 10)
        self.create_subscription(
            GoalStatusArray,
            "/navigate_to_pose/_action/status",
            self._action_status,
            10,
        )
        self.create_subscription(
            NavigateToPose.Impl.FeedbackMessage,
            "/navigate_to_pose/_action/feedback",
            self._feedback,
            10,
        )
        self.create_subscription(
            TwistStamped,
            "/mobile_base_controller/cmd_vel_out",
            self._command,
            20,
        )
        self.create_subscription(Log, "/rosout", self._log, 50)

    def _payload(self, message):
        try:
            payload = json.loads(message.data)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload if payload.get("request_id") == self.request_id else None

    def _decision(self, message):
        payload = self._payload(message)
        if payload is not None:
            self.decision = payload

    def _route(self, message):
        payload = self._payload(message)
        if payload is not None:
            self.route_requests.append(payload)

    def _escort(self, message):
        payload = self._payload(message)
        if payload is None:
            return
        if not self.escort_states or (
            self.escort_states[-1].get("state") != payload.get("state")
        ):
            self.escort_states.append(payload)

    def _result(self, message):
        payload = self._payload(message)
        if payload is None:
            return
        self.navigation_result = payload
        self.navigation_end_sim = self._sim_time()
        self.navigation_end_wall = time.monotonic()
        self._finished = True

    def _people(self, message):
        self.people_messages += 1
        self.people_identifiers.update(
            person.identifier for person in message.pedestrians
        )

    def _action_status(self, message):
        active = {GoalStatus.STATUS_ACCEPTED, GoalStatus.STATUS_EXECUTING}
        if self.navigation_start_sim is None and any(
            status.status in active for status in message.status_list
        ):
            self.navigation_start_sim = self._sim_time()
            self.navigation_start_wall = time.monotonic()

    def _feedback(self, message):
        self.maximum_recoveries = max(
            self.maximum_recoveries,
            int(message.feedback.number_of_recoveries),
        )

    def _models(self, message):
        if self.navigation_start_sim is None or self._finished:
            return
        indices = {name: index for index, name in enumerate(message.name)}
        robot_index = indices.get("tiago")
        person_index = indices.get(self.person_model)
        if robot_index is None or person_index is None:
            return
        robot_pose = message.pose[robot_index].position
        person_pose = message.pose[person_index].position
        robot = (robot_pose.x, robot_pose.y)
        person = (person_pose.x, person_pose.y)
        if self._previous_robot_position is not None:
            self.physical_path_length += math.dist(
                robot, self._previous_robot_position
            )
        self._previous_robot_position = robot
        self.minimum_person_distance = min(
            self.minimum_person_distance, math.dist(robot, person)
        )
        if self.initial_person_pose is None:
            self.initial_person_pose = list(person)

    def _command(self, message):
        self.latest_command = (
            message.twist.linear.x,
            message.twist.angular.z,
        )

    def _log(self, message):
        if "failed to make progress" in message.msg.lower():
            self.no_progress_failures += 1

    def _sim_time(self):
        return self.get_clock().now().nanoseconds / 1.0e9


def record(args):
    rclpy.init()
    probe = ComparisonProbe(args.request_id, args.person_id, args.person_model)
    request = {
        "request_id": args.request_id,
        "session_id": args.session_id,
        "intent": "recommend_and_prepare_navigation",
        "constraints": {"style": "impressionism"},
    }
    try:
        ready_deadline = time.monotonic() + 30.0
        while (
            probe.request_publisher.get_subscription_count() < 1
            and time.monotonic() < ready_deadline
        ):
            rclpy.spin_once(probe, timeout_sec=0.1)
        message = String()
        message.data = json.dumps(request)
        probe.request_publisher.publish(message)

        deadline = time.monotonic() + args.timeout
        while probe.navigation_result is None and time.monotonic() < deadline:
            rclpy.spin_once(probe, timeout_sec=0.1)
        drain_deadline = time.monotonic() + 2.0
        while time.monotonic() < drain_deadline:
            rclpy.spin_once(probe, timeout_sec=0.05)

        result = probe.navigation_result or {}
        escort_sequence = [item.get("state") for item in probe.escort_states]
        terminal_zero = all(abs(value) <= 1.0e-3 for value in probe.latest_command)
        checks = {
            "reasoning_selected_impressionism": (
                probe.decision is not None
                and probe.decision.get("selected_room") == "impressionism_hall"
            ),
            "exactly_one_north_route": (
                len(probe.route_requests) == 1
                and probe.route_requests[0].get("route") == "north_gallery"
            ),
            "navigation_succeeded": result.get("status") == "succeeded",
            "candidate_reached": result.get("candidate_reached") is True,
            "escort_completed": escort_sequence == EXPECTED_ESCORT,
            "people_received": (
                probe.people_messages > 0
                and args.person_id in probe.people_identifiers
                and "visitor_1" in probe.people_identifiers
            ),
            "navigation_timing_observed": (
                probe.navigation_start_sim is not None
                and probe.navigation_end_sim is not None
            ),
            "terminal_cmd_vel_zero": terminal_zero,
            "no_progress_failures": probe.no_progress_failures == 0,
        }
        report = {
            "variant": args.variant,
            "request": request,
            "assistant_response": probe.decision,
            "route_requests": probe.route_requests,
            "navigation_result": result,
            "escort_sequence": escort_sequence,
            "person_id": args.person_id,
            "person_model": args.person_model,
            "person_initial_pose": probe.initial_person_pose,
            "people_messages": probe.people_messages,
            "people_identifiers": sorted(probe.people_identifiers),
            "navigation_simulated_time_sec": elapsed(
                probe.navigation_start_sim, probe.navigation_end_sim
            ),
            "navigation_wall_time_sec": elapsed(
                probe.navigation_start_wall, probe.navigation_end_wall
            ),
            "physical_path_length_m": probe.physical_path_length,
            "minimum_person_distance_m": finite_or_none(
                probe.minimum_person_distance
            ),
            "maximum_recoveries": probe.maximum_recoveries,
            "no_progress_failures": probe.no_progress_failures,
            "terminal_cmd_vel": {
                "linear_x": probe.latest_command[0],
                "angular_z": probe.latest_command[1],
                "zero": terminal_zero,
            },
            "checks": checks,
            "status": "passed" if all(checks.values()) else "failed",
        }
        write_report(args.output, report)
        return 0 if report["status"] == "passed" else 3
    finally:
        probe.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def compare(args):
    baseline = read_report(args.baseline)
    social = read_report(args.social)
    baseline_clearance = baseline.get("minimum_person_distance_m")
    social_clearance = social.get("minimum_person_distance_m")
    delta = None
    if baseline_clearance is not None and social_clearance is not None:
        delta = social_clearance - baseline_clearance
    same_person_pose = positions_equal(
        baseline.get("person_initial_pose"), social.get("person_initial_pose")
    )
    technical_pass = all(
        report.get("status") == "passed" for report in (baseline, social)
    ) and same_person_pose
    behavioral_pass = (
        technical_pass
        and delta is not None
        and delta >= args.minimum_clearance_delta
        and social_clearance > 0.44
        and social.get("maximum_recoveries") == 0
        and social.get("no_progress_failures") == 0
    )
    report = {
        "technical_status": "passed" if technical_pass else "failed",
        "behavioral_status": "passed" if behavioral_pass else "failed",
        "same_person_pose": same_person_pose,
        "minimum_required_clearance_delta_m": args.minimum_clearance_delta,
        "clearance_delta_m": delta,
        "baseline": summary(baseline),
        "social": summary(social),
    }
    write_report(args.output, report)
    return 0 if technical_pass and behavioral_pass else 3


def elapsed(start, end):
    return end - start if start is not None and end is not None else None


def finite_or_none(value):
    return value if math.isfinite(value) else None


def positions_equal(first, second):
    return (
        isinstance(first, list)
        and isinstance(second, list)
        and len(first) == len(second) == 2
        and math.dist(first, second) <= 1.0e-6
    )


def summary(report):
    return {
        key: report.get(key)
        for key in (
            "variant",
            "navigation_simulated_time_sec",
            "navigation_wall_time_sec",
            "physical_path_length_m",
            "minimum_person_distance_m",
            "maximum_recoveries",
            "no_progress_failures",
            "terminal_cmd_vel",
            "escort_sequence",
            "navigation_result",
        )
    }


def read_report(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_report(path, report):
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def parse_args():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    recorder = subparsers.add_parser("record")
    recorder.add_argument("--variant", choices=("baseline", "social"), required=True)
    recorder.add_argument("--request-id", required=True)
    recorder.add_argument("--session-id", default="session_1")
    recorder.add_argument("--person-id", default="guide_1")
    recorder.add_argument("--person-model", default="guide_marker")
    recorder.add_argument("--timeout", type=float, default=1500.0)
    recorder.add_argument("--output", type=Path, required=True)
    recorder.set_defaults(function=record)

    comparator = subparsers.add_parser("compare")
    comparator.add_argument("--baseline", type=Path, required=True)
    comparator.add_argument("--social", type=Path, required=True)
    comparator.add_argument("--minimum-clearance-delta", type=float, default=0.01)
    comparator.add_argument("--output", type=Path, required=True)
    comparator.set_defaults(function=compare)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    raise SystemExit(arguments.function(arguments))
