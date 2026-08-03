"""Move the Gazebo visitor marker for one deterministic escort demo."""

import json
import math

import rclpy
from gazebo_msgs.msg import EntityState, ModelStates
from gazebo_msgs.srv import SetEntityState
from rclpy.node import Node
from std_msgs.msg import String

from museum_assistant.scripted_visitor import LagRecoverScenario


class ScriptedVisitorNode(Node):
    def __init__(self):
        super().__init__("scripted_visitor_node")
        self.declare_parameter("visitor_model_name", "visitor_marker")
        self.declare_parameter("robot_model_name", "tiago")
        self.declare_parameter("follow_distance", 1.5)
        self.declare_parameter("follow_speed", 0.5)
        self.declare_parameter("catchup_speed", 0.8)
        self.declare_parameter("lag_after_seconds", 5.0)
        self.declare_parameter("update_rate", 5.0)

        self._visitor_model_name = str(
            self.get_parameter("visitor_model_name").value
        )
        self._robot_model_name = str(
            self.get_parameter("robot_model_name").value
        )
        self._update_rate = float(self.get_parameter("update_rate").value)
        if (
            not self._visitor_model_name
            or not self._robot_model_name
            or not math.isfinite(self._update_rate)
            or self._update_rate <= 0.0
        ):
            raise ValueError("Model names and update_rate must be valid.")

        self._scenario = LagRecoverScenario(
            follow_distance=float(
                self.get_parameter("follow_distance").value
            ),
            follow_speed=float(self.get_parameter("follow_speed").value),
            catchup_speed=float(
                self.get_parameter("catchup_speed").value
            ),
            lag_after_seconds=float(
                self.get_parameter("lag_after_seconds").value
            ),
        )
        self._task_key: tuple[str, str, str] | None = None
        self._visitor_position: tuple[float, float] | None = None
        self._robot_position: tuple[float, float] | None = None
        self._visitor_z = 0.0
        self._visitor_orientation = (0.0, 0.0, 0.0, 1.0)
        self._set_state_future = None
        self._pending_position: tuple[float, float] | None = None
        self._last_tick: float | None = None
        self._service_ready_announced = False

        self._model_subscription = self.create_subscription(
            ModelStates,
            "/gazebo/model_states",
            self._handle_model_states,
            10,
        )
        self._escort_subscription = self.create_subscription(
            String,
            "/museum/escort_state",
            self._handle_escort_state,
            10,
        )
        self._set_state_client = self.create_client(
            SetEntityState,
            "/gazebo/set_entity_state",
        )
        self._timer = self.create_timer(
            1.0 / self._update_rate,
            self._update,
        )
        self.get_logger().info(
            "Scripted visitor is idle until a new escorting task is observed"
        )

    def _handle_model_states(self, msg: ModelStates) -> None:
        indices = {
            name: index
            for index, name in enumerate(msg.name)
            if index < len(msg.pose)
        }
        visitor_index = indices.get(self._visitor_model_name)
        robot_index = indices.get(self._robot_model_name)
        if visitor_index is None or robot_index is None:
            return

        visitor_pose = msg.pose[visitor_index]
        robot_pose = msg.pose[robot_index]
        self._visitor_position = (
            visitor_pose.position.x,
            visitor_pose.position.y,
        )
        self._robot_position = (
            robot_pose.position.x,
            robot_pose.position.y,
        )
        self._visitor_z = visitor_pose.position.z
        self._visitor_orientation = (
            visitor_pose.orientation.x,
            visitor_pose.orientation.y,
            visitor_pose.orientation.z,
            visitor_pose.orientation.w,
        )

    def _handle_escort_state(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warning(
                f"Ignoring malformed escort-state JSON: {exc}"
            )
            return
        if not isinstance(payload, dict):
            return

        state = payload.get("state")
        if state not in {"escorting", "waiting", "arrived", "lost"}:
            return
        task_key = tuple(
            str(payload.get(field, ""))
            for field in ("request_id", "session_id", "selected_room")
        )
        if state == "escorting" and task_key != self._task_key:
            self._task_key = task_key
            self._scenario.reset()

        previous_phase = self._scenario.phase
        self._scenario.handle_escort_state(state, now=self._now())
        if self._scenario.phase is not previous_phase:
            self.get_logger().info(
                f"Scripted visitor phase: {self._scenario.phase.value}"
            )

    def _update(self) -> None:
        now = self._now()
        if self._last_tick is None:
            self._last_tick = now
            return
        dt = min(max(0.0, now - self._last_tick), 1.0 / self._update_rate)
        self._last_tick = now

        if (
            self._visitor_position is None
            or self._robot_position is None
            or self._set_state_future is not None
        ):
            return

        next_position = self._scenario.step(
            self._visitor_position,
            self._robot_position,
            now=now,
            dt=dt,
        )
        if next_position == self._visitor_position:
            return

        if not self._set_state_client.service_is_ready():
            if not self._service_ready_announced:
                self.get_logger().warning(
                    "Waiting for /gazebo/set_entity_state"
                )
                self._service_ready_announced = True
            return
        if self._service_ready_announced:
            self.get_logger().info("Gazebo SetEntityState service is ready")
            self._service_ready_announced = False

        request = SetEntityState.Request()
        request.state = EntityState()
        request.state.name = self._visitor_model_name
        request.state.reference_frame = "world"
        request.state.pose.position.x = next_position[0]
        request.state.pose.position.y = next_position[1]
        request.state.pose.position.z = self._visitor_z
        (
            request.state.pose.orientation.x,
            request.state.pose.orientation.y,
            request.state.pose.orientation.z,
            request.state.pose.orientation.w,
        ) = self._visitor_orientation

        self._pending_position = next_position
        self._set_state_future = self._set_state_client.call_async(request)
        self._set_state_future.add_done_callback(self._handle_set_state_result)

    def _handle_set_state_result(self, future) -> None:
        pending_position = self._pending_position
        self._pending_position = None
        self._set_state_future = None
        try:
            response = future.result()
        except Exception as exc:
            self.get_logger().warning(
                f"Gazebo SetEntityState call failed: {exc}"
            )
            return

        if response is None or not response.success:
            self.get_logger().warning(
                "Gazebo rejected the scripted visitor movement"
            )
            return
        if pending_position is not None:
            self._visitor_position = pending_position

    def _now(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9


def main(args=None):
    rclpy.init(args=args)
    node = ScriptedVisitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
