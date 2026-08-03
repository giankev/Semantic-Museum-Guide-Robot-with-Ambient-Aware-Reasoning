"""ROS text interface with deterministic parsing and one-at-a-time Groq fallback."""

import json
import os
import queue
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from museum_assistant.language_parser import (
    DEFAULT_GROQ_BASE_URL,
    DEFAULT_GROQ_MODEL,
    GroqLanguageClient,
    LanguageRouteResult,
    parse_deterministic,
    route_text,
)


class LanguageNode(Node):
    def __init__(self):
        super().__init__("language_node")
        self._active_session_id = None
        self._request_number = 0
        self._fallback_busy = False
        self._fallback_results = queue.SimpleQueue()

        self._request_publisher = self.create_publisher(
            String,
            "/museum/user_request",
            10,
        )
        self._text_subscription = self.create_subscription(
            String,
            "/museum/user_text",
            self._handle_user_text,
            10,
        )
        self._session_subscription = self.create_subscription(
            String,
            "/museum/session_state",
            self._handle_session_state,
            10,
        )
        self._result_timer = self.create_timer(0.1, self._publish_fallback_result)

        api_key = os.environ.get("GROQ_API_KEY")
        self._groq = None
        self._groq_model = (
            os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        )
        if api_key:
            try:
                self._groq = GroqLanguageClient(
                    api_key=api_key,
                    base_url=(
                        os.environ.get("GROQ_BASE_URL")
                        or DEFAULT_GROQ_BASE_URL
                    ),
                    model=self._groq_model,
                )
            except Exception as exc:
                self.get_logger().warning(
                    "Groq fallback is unavailable "
                    f"({type(exc).__name__}); deterministic parsing remains active"
                )
        else:
            self.get_logger().info(
                "Groq fallback is unavailable because GROQ_API_KEY is absent; "
                "deterministic parsing remains active"
            )

        self.get_logger().info("Subscribed to /museum/user_text")
        self.get_logger().info(
            "Publishing validated requests on /museum/user_request"
        )

    def _handle_user_text(self, msg: String) -> None:
        self._request_number += 1
        request_id = f"text_{self._request_number}"
        session_id = self._active_session_id

        if parse_deterministic(msg.data) is not None:
            result = route_text(
                msg.data,
                request_id=request_id,
                session_id=session_id,
            )
            self._handle_route_result(result)
            return

        if self._groq is None:
            self.get_logger().warning(
                f"No request published for {request_id}: Groq fallback unavailable"
            )
            return
        if self._fallback_busy:
            self.get_logger().warning(
                f"Ignoring unresolved {request_id}: a Groq request is already active"
            )
            return

        self._fallback_busy = True
        worker = threading.Thread(
            target=self._run_groq_fallback,
            args=(msg.data, request_id, session_id),
            daemon=True,
            name="museum_groq_fallback",
        )
        worker.start()

    def _run_groq_fallback(
        self,
        text: str,
        request_id: str,
        session_id: str | None,
    ) -> None:
        started = time.monotonic()
        try:
            result = route_text(
                text,
                request_id=request_id,
                session_id=session_id,
                llm_callable=self._groq.translate,
            )
        except Exception as exc:
            result = LanguageRouteResult(
                request=None,
                source="groq",
                status=f"worker_error:{type(exc).__name__}",
            )
        self._fallback_results.put((result, time.monotonic() - started))

    def _publish_fallback_result(self) -> None:
        try:
            result, latency = self._fallback_results.get_nowait()
        except queue.Empty:
            return

        self._fallback_busy = False
        fields = ",".join(result.response_fields) or "none"
        self.get_logger().info(
            "Groq fallback completed "
            f"model={self._groq_model} latency_seconds={latency:.3f} "
            f"response_fields={fields}"
        )
        self._handle_route_result(result)

    def _handle_route_result(self, result: LanguageRouteResult) -> None:
        if result.request is None:
            self.get_logger().warning(
                "No request published: "
                f"source={result.source} status={result.status}"
            )
            return

        request_data = result.request.to_dict()
        if result.source == "groq":
            self.get_logger().info(
                "Validated Groq candidate: "
                f"{json.dumps(result.candidate, sort_keys=True)}"
            )
        self.get_logger().info(
            "Validated StructuredRequest: "
            f"{json.dumps(request_data, sort_keys=True)}"
        )
        output = String()
        output.data = json.dumps(request_data)
        self._request_publisher.publish(output)

    def _handle_session_state(self, msg: String) -> None:
        try:
            session = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning("Ignoring invalid session-state JSON")
            return
        if not isinstance(session, dict):
            self.get_logger().warning("Ignoring non-object session state")
            return

        session_id = session.get("session_id")
        if (
            session.get("state") == "active"
            and isinstance(session_id, str)
            and session_id.strip()
        ):
            self._active_session_id = session_id
        elif session_id == self._active_session_id:
            self._active_session_id = None


def main(args=None):
    rclpy.init(args=args)
    node = LanguageNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
