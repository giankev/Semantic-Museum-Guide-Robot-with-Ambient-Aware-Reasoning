"""Send approved decisions to Nav2 with minimal escort supervision."""

import json
import math

import rclpy
from action_msgs.msg import GoalStatus
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String

from museum_assistant.escort import EscortState, EscortSupervisor
from museum_assistant.semantic_navigation import (
    navigation_pose_from_decision,
)


class SemanticNavigationNode(Node):
    def __init__(self):
        super().__init__("semantic_navigation_node")
        self.client = ActionClient(
            self,
            NavigateToPose,
            "navigate_to_pose",
        )
        self.result_publisher = self.create_publisher(
            String,
            "/museum/navigation_result",
            10,
        )
        self.escort_publisher = self.create_publisher(
            String,
            "/museum/escort_state",
            10,
        )
        self.response_subscription = self.create_subscription(
            String,
            "/museum/assistant_response",
            self._handle_response,
            10,
        )
        self.visitor_subscription = self.create_subscription(
            String,
            "/museum/visitor_observation",
            self._handle_visitor_observation,
            10,
        )

        self.declare_parameter("resume_distance", 2.0)
        self.declare_parameter("wait_distance", 3.0)
        self.declare_parameter("lost_distance", 8.0)
        self.declare_parameter("arrival_distance", 2.5)
        self.declare_parameter("wait_delay", 3.0)
        self.declare_parameter("absence_timeout", 3.0)
        self.escort = EscortSupervisor(
            resume_distance=float(
                self.get_parameter("resume_distance").value
            ),
            wait_distance=float(
                self.get_parameter("wait_distance").value
            ),
            lost_distance=float(
                self.get_parameter("lost_distance").value
            ),
            arrival_distance=float(
                self.get_parameter("arrival_distance").value
            ),
            wait_delay=float(self.get_parameter("wait_delay").value),
            absence_timeout=float(
                self.get_parameter("absence_timeout").value
            ),
        )

        self._task_active = False
        self._active_correlation: dict[str, str] = {}
        self._active_nav_pose: tuple[float, float, float] | None = None
        self._goal_request_in_flight = False
        self._cancel_request_in_flight = False
        self._goal_handle = None
        self._cancel_reason: str | None = None

        self.get_logger().info(
            "Waiting for executable decisions on "
            "/museum/assistant_response"
        )
        self.get_logger().info(
            "Monitoring visitor distance on "
            "/museum/visitor_observation"
        )

    def _handle_response(self, msg: String) -> None:
        try:
            decision = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warning(
                f"Ignoring malformed assistant-response JSON: {exc}"
            )
            return

        nav_pose = navigation_pose_from_decision(decision)
        if nav_pose is None:
            return

        if self._task_active:
            self.get_logger().warning(
                "Ignoring navigation decision while an escort task is active"
            )
            return

        self._task_active = True
        self._active_nav_pose = nav_pose
        self._active_correlation = {
            field: decision[field]
            for field in ("request_id", "session_id", "selected_room")
            if isinstance(decision.get(field), str)
        }
        self._cancel_reason = None
        self.escort.start()
        self._publish_escort_state()
        self._send_navigation_goal()

    def _handle_visitor_observation(self, msg: String) -> None:
        try:
            observation = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warning(
                f"Ignoring malformed visitor-observation JSON: {exc}"
            )
            return

        if not isinstance(observation, dict):
            self.get_logger().warning(
                "Ignoring visitor observation that is not a JSON object"
            )
            return

        active_session = self._active_correlation.get("session_id")
        observation_session = observation.get("session_id")
        if (
            self._task_active
            and active_session is not None
            and observation_session != active_session
        ):
            self.get_logger().warning(
                "Ignoring visitor observation for a different session"
            )
            return

        present = observation.get("present")
        if not isinstance(present, bool):
            self.get_logger().warning(
                "Ignoring visitor observation without boolean present"
            )
            return
        distance = observation.get("distance_to_robot")

        previous_state = self.escort.state
        try:
            current_state = self.escort.observe(
                present=present,
                distance_to_robot=distance,
                now=self.get_clock().now().nanoseconds / 1e9,
            )
        except ValueError as exc:
            self.get_logger().warning(
                f"Ignoring invalid visitor observation: {exc}"
            )
            return

        if not self._task_active or current_state is None:
            return

        self._publish_escort_state()
        if current_state is previous_state:
            return

        self.get_logger().info(
            f"Escort state changed to {current_state.value}"
        )
        if current_state is EscortState.WAITING:
            if not self.escort.navigation_reached_destination:
                self._pause_navigation()
        elif current_state is EscortState.ESCORTING:
            if not self.escort.navigation_reached_destination:
                self._resume_navigation()
        elif current_state is EscortState.LOST:
            self._handle_lost_visitor()
        elif current_state is EscortState.ARRIVED:
            self._release_task(keep_escort_state=True)

    def _send_navigation_goal(self) -> None:
        if (
            not self._task_active
            or self._active_nav_pose is None
            or self.escort.state is not EscortState.ESCORTING
            or self.escort.navigation_reached_destination
            or self._goal_request_in_flight
            or self._goal_handle is not None
        ):
            return

        if not self.client.wait_for_server(timeout_sec=1.0):
            self.get_logger().warning(
                "NavigateToPose action server is unavailable"
            )
            self._finish_navigation_failure("server_unavailable")
            return

        x, y, yaw = self._active_nav_pose
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.position.z = 0.0
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)

        self._goal_request_in_flight = True
        try:
            future = self.client.send_goal_async(goal)
        except Exception as exc:
            self._goal_request_in_flight = False
            self.get_logger().error(
                f"Failed to start navigation goal request: {exc}"
            )
            self._finish_navigation_failure("rejected")
            return
        future.add_done_callback(self._handle_goal_response)

    def _handle_goal_response(self, future) -> None:
        self._goal_request_in_flight = False
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.get_logger().error(f"Failed to send navigation goal: {exc}")
            self._finish_navigation_failure("rejected")
            return

        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().warning("Navigation goal was rejected")
            self._finish_navigation_failure("rejected")
            return

        self._goal_handle = goal_handle
        self.get_logger().info("Navigation goal accepted")
        self._publish_result("accepted")
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._handle_navigation_result)

        if self._cancel_reason is not None:
            self._cancel_current_goal()

    def _handle_navigation_result(self, future) -> None:
        try:
            result = future.result()
        except Exception as exc:
            self.get_logger().error(
                f"Navigation goal failed without a result: {exc}"
            )
            self._finish_navigation_failure("aborted")
            return

        status_by_code = {
            GoalStatus.STATUS_SUCCEEDED: "succeeded",
            GoalStatus.STATUS_ABORTED: "aborted",
            GoalStatus.STATUS_CANCELED: "canceled",
        }
        status = (
            status_by_code.get(result.status, "aborted")
            if result is not None
            else "aborted"
        )
        cancel_reason = self._cancel_reason
        self._goal_handle = None
        self._goal_request_in_flight = False
        self._cancel_request_in_flight = False
        self._cancel_reason = None

        self.get_logger().info(f"Navigation goal finished: {status}")
        self._publish_result(status)

        if status == "succeeded":
            previous_state = self.escort.state
            current_state = self.escort.navigation_succeeded()
            if current_state is not None:
                self._publish_escort_state()
            if current_state is not previous_state:
                self.get_logger().info(
                    f"Escort state changed to {current_state.value}"
                )
            if current_state in {EscortState.ARRIVED, EscortState.LOST}:
                self._release_task(keep_escort_state=True)
            return

        if status == "canceled" and cancel_reason == "pause":
            if self.escort.state is EscortState.ESCORTING:
                self._send_navigation_goal()
            return

        keep_state = self.escort.state is EscortState.LOST
        self._release_task(keep_escort_state=keep_state)

    def _pause_navigation(self) -> None:
        self._cancel_reason = "pause"
        self._cancel_current_goal()

    def _resume_navigation(self) -> None:
        if self._goal_handle is None and not self._goal_request_in_flight:
            self._send_navigation_goal()

    def _handle_lost_visitor(self) -> None:
        self._cancel_reason = "lost"
        if self._goal_handle is not None:
            self._cancel_current_goal()
        elif not self._goal_request_in_flight:
            self._release_task(keep_escort_state=True)

    def _cancel_current_goal(self) -> None:
        if self._goal_handle is None or self._cancel_request_in_flight:
            return

        self._cancel_request_in_flight = True
        try:
            future = self._goal_handle.cancel_goal_async()
        except Exception as exc:
            self._cancel_request_in_flight = False
            self.get_logger().error(
                f"Failed to request navigation cancellation: {exc}"
            )
            return
        future.add_done_callback(self._handle_cancel_response)

    def _handle_cancel_response(self, future) -> None:
        self._cancel_request_in_flight = False
        try:
            response = future.result()
        except Exception as exc:
            self.get_logger().error(
                f"Navigation cancellation request failed: {exc}"
            )
            return

        if response is None or not response.goals_canceling:
            self.get_logger().warning(
                "NavigateToPose did not accept the cancellation request"
            )

    def _publish_result(self, status: str) -> None:
        payload = dict(self._active_correlation)
        payload["status"] = status
        msg = String()
        msg.data = json.dumps(payload)
        self.result_publisher.publish(msg)

    def _publish_escort_state(self) -> None:
        if self.escort.state is None:
            return

        payload = dict(self._active_correlation)
        payload["state"] = self.escort.state.value
        distance = self.escort.distance_to_robot
        if distance is not None:
            payload["distance_to_robot"] = distance

        msg = String()
        msg.data = json.dumps(payload)
        self.escort_publisher.publish(msg)

    def _finish_navigation_failure(self, status: str) -> None:
        self._publish_result(status)
        keep_state = self.escort.state is EscortState.LOST
        self._release_task(keep_escort_state=keep_state)

    def _release_task(self, *, keep_escort_state: bool) -> None:
        self._task_active = False
        self._active_nav_pose = None
        self._goal_request_in_flight = False
        self._cancel_request_in_flight = False
        self._goal_handle = None
        self._cancel_reason = None
        self._active_correlation = {}
        if not keep_escort_state:
            self.escort.stop()


def main(args=None):
    rclpy.init(args=args)
    node = SemanticNavigationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
