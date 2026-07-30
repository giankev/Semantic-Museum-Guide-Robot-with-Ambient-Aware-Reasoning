from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="semantic_navigation_node",
                name="semantic_navigation_node",
                output="screen",
                parameters=[{"use_sim_time": True}],
            ),
        ]
    )
