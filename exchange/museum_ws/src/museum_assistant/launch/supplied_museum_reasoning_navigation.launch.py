"""End-to-end deterministic reasoning and supplied-museum navigation."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    museum_share = FindPackageShare("museum_assistant")
    navigation_launch = PathJoinSubstitution(
        [
            museum_share,
            "launch",
            "supplied_museum_demo_navigation.launch.py",
        ]
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "gzclient",
                default_value="False",
                choices=["True", "False"],
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(navigation_launch),
                launch_arguments={
                    "gzclient": LaunchConfiguration("gzclient")
                }.items(),
            ),
            Node(
                package="museum_assistant",
                executable="reasoning_node",
                name="reasoning_node",
                output="screen",
                parameters=[{"use_sim_time": True}],
            ),
            Node(
                package="museum_assistant",
                executable="semantic_route_dispatcher",
                name="semantic_route_dispatcher",
                output="screen",
                parameters=[{"use_sim_time": True}],
            ),
            Node(
                package="museum_assistant",
                executable="supplied_museum_route_runner_node",
                output="screen",
                parameters=[{"use_sim_time": True}],
            ),
        ]
    )
