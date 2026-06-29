from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    slam_params = PathJoinSubstitution(
        [FindPackageShare("museum_assistant"), "config", "slam_toolbox_museum.yaml"]
    )

    return LaunchDescription(
        [
            Node(
                package="slam_toolbox",
                executable="async_slam_toolbox_node",
                name="slam_toolbox",
                output="screen",
                parameters=[slam_params],
                remappings=[("scan", "/scan_raw")],
            ),
        ]
    )
