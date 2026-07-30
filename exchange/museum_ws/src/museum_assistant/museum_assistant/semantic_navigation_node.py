"""Send approved deterministic reasoning decisions to Nav2."""

import json
import math

import rclpy
from action_msgs.msg import GoalStatus
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String

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
        self.response_subscription = self.create_subscription(
            String,
            "/museum/assistant_response",
            self._handle_response,
            10,
        )
        self._goal_active = False
        self._active_correlation: dict[str, str] = {}
        self.get_logger().info(
            "Waiting for executable decisions on "
            "/museum/assistant_response"
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

        if self._goal_active:
            self.get_logger().warning(
                "Ignoring navigation decision while a goal is active"
            )
            return

        self._goal_active = True
        self._active_correlation = {
            field: decision[field]
            for field in ("request_id", "session_id", "selected_room")
            if isinstance(decision.get(field), str)
        }

        if not self.client.wait_for_server(timeout_sec=1.0):
            self.get_logger().warning(
                "NavigateToPose action server is unavailable"
            )
            self._finish_goal("server_unavailable")
            return

        x, y, yaw = nav_pose
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.position.z = 0.0
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)

        try:
            future = self.client.send_goal_async(goal)
        except Exception as exc:
            self.get_logger().error(
                f"Failed to start navigation goal request: {exc}"
            )
            self._finish_goal("rejected")
            return
        future.add_done_callback(self._handle_goal_response)

    def _handle_goal_response(self, future) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.get_logger().error(f"Failed to send navigation goal: {exc}")
            self._finish_goal("rejected")
            return

        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().warning("Navigation goal was rejected")
            self._finish_goal("rejected")
            return

        self.get_logger().info("Navigation goal accepted")
        self._publish_result("accepted")
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._handle_navigation_result)

    def _handle_navigation_result(self, future) -> None:
        try:
            result = future.result()
        except Exception as exc:
            self.get_logger().error(
                f"Navigation goal failed without a result: {exc}"
            )
            self._finish_goal("aborted")
            return

        if result is None:
            self._finish_goal("aborted")
            return

        status_by_code = {
            GoalStatus.STATUS_SUCCEEDED: "succeeded",
            GoalStatus.STATUS_ABORTED: "aborted",
            GoalStatus.STATUS_CANCELED: "canceled",
        }
        status = status_by_code.get(result.status, "aborted")
        self.get_logger().info(f"Navigation goal finished: {status}")
        self._finish_goal(status)

    def _publish_result(self, status: str) -> None:
        payload = dict(self._active_correlation)
        payload["status"] = status
        msg = String()
        msg.data = json.dumps(payload)
        self.result_publisher.publish(msg)

    def _finish_goal(self, status: str) -> None:
        self._publish_result(status)
        self._goal_active = False
        self._active_correlation = {}


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
