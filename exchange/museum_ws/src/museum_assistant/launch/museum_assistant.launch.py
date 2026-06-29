from launch import LaunchDescription
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description():
    semantic_map = PathJoinSubstitution(
        [FindPackageShare("museum_assistant"), "config", "semantic_map.yaml"]
    )

    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="semantic_graph_node",
                name="semantic_graph_node",
                output="screen",
                parameters=[{"semantic_map": semantic_map}],
            ),
            Node(
                package="museum_assistant",
                executable="sensor_simulator_node",
                name="sensor_simulator_node",
                output="screen",
            ),
            Node(
                package="museum_assistant",
                executable="cli_node",
                name="cli_node",
                output="screen",
            ),
        ]
    )
