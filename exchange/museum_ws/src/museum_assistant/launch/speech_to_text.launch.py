"""Launch only the bounded file-based speech-to-text node."""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="speech_to_text_node",
                name="speech_to_text_node",
                output="screen",
            )
        ]
    )
