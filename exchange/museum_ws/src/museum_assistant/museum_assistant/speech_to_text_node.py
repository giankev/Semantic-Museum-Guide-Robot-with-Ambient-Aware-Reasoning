"""ROS adapter for bounded file-based speech transcription."""

import os

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from museum_assistant.speech_to_text import (
    DEFAULT_GROQ_BASE_URL,
    DEFAULT_GROQ_STT_MODEL,
    GroqTranscriptionClient,
    TranscriptionCoordinator,
    TranscriptionOutcome,
    publication_data,
)


class SpeechToTextNode(Node):
    def __init__(self):
        super().__init__("speech_to_text_node")
        model = os.environ.get("GROQ_STT_MODEL") or DEFAULT_GROQ_STT_MODEL
        client = GroqTranscriptionClient(
            api_key=os.environ.get("GROQ_API_KEY"),
            base_url=os.environ.get("GROQ_BASE_URL") or DEFAULT_GROQ_BASE_URL,
            model=model,
        )
        self._coordinator = TranscriptionCoordinator(client)

        self._text_publisher = self.create_publisher(
            String, "/museum/user_text", 10
        )
        self._status_publisher = self.create_publisher(
            String, "/museum/transcription_status", 10
        )
        self._audio_subscription = self.create_subscription(
            String, "/museum/audio_file", self._handle_audio_file, 10
        )
        self._result_timer = self.create_timer(0.1, self._publish_worker_result)

        self.get_logger().info(
            f"File-based transcription ready model={model}"
        )
        self.get_logger().info("Subscribed to /museum/audio_file")

    def _handle_audio_file(self, msg: String) -> None:
        rejected = self._coordinator.submit(msg.data)
        if rejected is not None:
            self._publish_outcome(rejected)

    def _publish_worker_result(self) -> None:
        outcome = self._coordinator.poll()
        if outcome is not None:
            self._publish_outcome(outcome)

    def _publish_outcome(self, outcome: TranscriptionOutcome) -> None:
        status_data, transcript = publication_data(outcome)
        status = String()
        status.data = status_data
        self._status_publisher.publish(status)

        safe_fields = (
            f"request_id={outcome.audio_request_id} status={outcome.status} "
            f"model={outcome.model} basename={outcome.audio_basename or 'none'}"
        )
        if outcome.file_size_bytes is not None:
            safe_fields += f" file_size={outcome.file_size_bytes}"
        if outcome.latency_seconds is not None:
            safe_fields += f" latency_seconds={outcome.latency_seconds:.3f}"

        if transcript is None:
            self.get_logger().warning(safe_fields)
            return

        text = String()
        text.data = transcript
        self._text_publisher.publish(text)
        self.get_logger().info(
            f"{safe_fields} transcript_characters={len(transcript)}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = SpeechToTextNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
