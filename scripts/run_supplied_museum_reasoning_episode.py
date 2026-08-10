#!/usr/bin/env python3
"""Publish a semantic request and record one correlated physical episode."""

import argparse
import json
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class EpisodeProbe(Node):
    def __init__(self, request_id: str):
        super().__init__("supplied_museum_reasoning_episode_probe")
        self.request_id = request_id
        self.decision = None
        self.transcriptions = []
        self.structured_requests = []
        self.route_requests = []
        self.escort_states = []
        self.navigation_result = None
        self.request_publisher = self.create_publisher(
            String, "/museum/user_request", 10
        )
        self.text_publisher = self.create_publisher(
            String, "/museum/user_text", 10
        )
        self.audio_publisher = self.create_publisher(
            String, "/museum/audio_file", 10
        )
        self.create_subscription(
            String, "/museum/user_text", self._transcription, 10
        )
        self.create_subscription(
            String, "/museum/user_request", self._structured_request, 10
        )
        self.create_subscription(
            String, "/museum/assistant_response", self._decision, 10
        )
        self.create_subscription(
            String,
            "/museum/supplied_route_request",
            self._route_request,
            10,
        )
        self.create_subscription(
            String, "/museum/navigation_result", self._result, 10
        )
        self.create_subscription(
            String, "/museum/escort_state", self._escort_state, 10
        )

    def _matching_payload(self, message: String):
        try:
            payload = json.loads(message.data)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload if payload.get("request_id") == self.request_id else None

    def _decision(self, message: String) -> None:
        payload = self._matching_payload(message)
        if payload is not None:
            self.decision = payload

    def _structured_request(self, message: String) -> None:
        payload = self._matching_payload(message)
        if payload is not None:
            self.structured_requests.append(payload)

    def _transcription(self, message: String) -> None:
        if message.data.strip():
            self.transcriptions.append(message.data.strip())

    def _route_request(self, message: String) -> None:
        payload = self._matching_payload(message)
        if payload is not None:
            self.route_requests.append(payload)

    def _result(self, message: String) -> None:
        payload = self._matching_payload(message)
        if payload is not None:
            self.navigation_result = payload

    def _escort_state(self, message: String) -> None:
        payload = self._matching_payload(message)
        if payload is None:
            return
        if (
            not self.escort_states
            or self.escort_states[-1].get("state") != payload.get("state")
        ):
            self.escort_states.append(payload)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--style", required=True)
    parser.add_argument("--avoid-crowd", action="store_true")
    parser.add_argument("--text")
    parser.add_argument("--audio-file")
    parser.add_argument("--expected-transcript")
    parser.add_argument("--expected-room", required=True)
    parser.add_argument("--expected-route", required=True)
    parser.add_argument("--expected-candidate", required=True)
    parser.add_argument("--expected-escort-sequence", nargs="+")
    parser.add_argument("--expected-navigation-sequence", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1500.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    probe = EpisodeProbe(args.request_id)
    constraints = {"style": args.style}
    if args.avoid_crowd:
        constraints["avoid_crowd"] = True
    request = {
        "request_id": args.request_id,
        "session_id": args.session_id,
        "intent": "recommend_and_prepare_navigation",
        "constraints": constraints,
    }
    try:
        ready_deadline = time.monotonic() + 30.0
        if args.audio_file:
            publisher = probe.audio_publisher
            input_data = args.audio_file
            topic = "/museum/audio_file"
        elif args.text:
            publisher = probe.text_publisher
            input_data = args.text
            topic = "/museum/user_text"
        else:
            publisher = probe.request_publisher
            input_data = json.dumps(request)
            topic = "/museum/user_request"
        while (
            publisher.get_subscription_count() < 1
            and time.monotonic() < ready_deadline
        ):
            rclpy.spin_once(probe, timeout_sec=0.10)
        if publisher.get_subscription_count() < 1:
            raise RuntimeError(f"no subscriber became ready on {topic}")

        message = String()
        message.data = input_data
        publisher.publish(message)
        deadline = time.monotonic() + args.timeout
        while probe.navigation_result is None and time.monotonic() < deadline:
            rclpy.spin_once(probe, timeout_sec=0.10)
        if probe.navigation_result is None:
            raise RuntimeError("timed out waiting for correlated navigation result")

        drain_deadline = time.monotonic() + 1.0
        while time.monotonic() < drain_deadline:
            rclpy.spin_once(probe, timeout_sec=0.05)

        report = {
            "request": request,
            "input_audio_file": args.audio_file,
            "input_text": args.text,
            "transcriptions": probe.transcriptions,
            "structured_requests": probe.structured_requests,
            "assistant_response": probe.decision,
            "route_requests": probe.route_requests,
            "escort_states": probe.escort_states,
            "navigation_result": probe.navigation_result,
        }
        checks = {
            "exactly_one_structured_request": (
                len(probe.structured_requests) == 1
            ),
            "structured_request_matches": (
                len(probe.structured_requests) == 1
                and probe.structured_requests[0] == request
            ),
            "reasoning_not_bypassed": probe.decision is not None,
            "decision_success": (
                probe.decision is not None
                and probe.decision.get("status") == "success"
                and probe.decision.get("skill") == "navigate_to"
                and probe.decision.get("selected_room") == args.expected_room
            ),
            "exactly_one_route_request": len(probe.route_requests) == 1,
            "route_resolved": (
                len(probe.route_requests) == 1
                and probe.route_requests[0].get("route")
                == args.expected_route
            ),
            "correlation_preserved": all(
                payload is not None
                and payload.get("request_id") == args.request_id
                and payload.get("session_id") == args.session_id
                and payload.get("selected_room") == args.expected_room
                for payload in (
                    probe.decision,
                    probe.route_requests[0]
                    if len(probe.route_requests) == 1
                    else None,
                    probe.navigation_result,
                )
            ),
            "nav2_succeeded": (
                probe.navigation_result.get("status") == "succeeded"
                and probe.navigation_result.get("nav2_succeeded") is True
            ),
            "final_candidate_reached": (
                probe.navigation_result.get("final_candidate")
                == args.expected_candidate
                and probe.navigation_result.get("candidate_reached") is True
                and probe.navigation_result.get("gazebo_target_error_m")
                is not None
                and probe.navigation_result["gazebo_target_error_m"] <= 0.50
            ),
        }
        if args.audio_file:
            checks["exactly_one_transcription"] = (
                len(probe.transcriptions) == 1
            )
            if args.expected_transcript:
                checks["transcription_matches"] = (
                    probe.transcriptions == [args.expected_transcript]
                )
        if args.expected_escort_sequence is not None:
            checks["escort_sequence"] = [
                payload.get("state") for payload in probe.escort_states
            ] == args.expected_escort_sequence
        if args.expected_navigation_sequence is not None:
            events = probe.navigation_result.get("navigation_events", [])
            checks["navigation_sequence"] = [
                event.get("status") for event in events
            ] == args.expected_navigation_sequence
            goal_uuids = probe.navigation_result.get("goal_uuids", [])
            checks["unique_goal_uuids"] = (
                len(goal_uuids) == len(set(goal_uuids))
            )
        report["checks"] = checks
        report["status"] = "passed" if all(checks.values()) else "failed"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["status"] != "passed":
            raise SystemExit(3)
    finally:
        probe.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
