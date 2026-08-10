#!/usr/bin/env python3
"""Capture timestamped JSON payloads from one std_msgs/String topic."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class JsonStringCapture(Node):
    def __init__(self, topic: str, output: Path) -> None:
        super().__init__("benchmark_json_string_capture")
        self._stream = output.open("a", encoding="utf-8", buffering=1)
        self.create_subscription(String, topic, self._handle_message, 10)

    def _handle_message(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
        except json.JSONDecodeError:
            payload = {"raw": message.data}
        record = {
            "received_monotonic_s": time.monotonic(),
            "received_utc": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        self._stream.write(json.dumps(record, sort_keys=True) + "\n")

    def close(self) -> None:
        self._stream.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    rclpy.init()
    node = JsonStringCapture(args.topic, args.output)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
