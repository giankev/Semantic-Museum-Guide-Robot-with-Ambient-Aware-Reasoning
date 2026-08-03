from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="semantic_graph_node",
                name="semantic_graph_node",
                output="screen",
            ),
        ]
    )
