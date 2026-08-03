from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="language_node",
                name="language_node",
                output="screen",
            ),
        ]
    )
