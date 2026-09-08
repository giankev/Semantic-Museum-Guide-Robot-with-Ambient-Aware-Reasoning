"""End-to-end deterministic reasoning and supplied-museum navigation."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
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
            DeclareLaunchArgument(
                "nav2_params_file",
                default_value=PathJoinSubstitution(
                    [museum_share, "config", "nav2_supplied_demo.yaml"]
                ),
            ),
            DeclareLaunchArgument(
                "publish_people",
                default_value="False",
                choices=["True", "False"],
            ),
            DeclareLaunchArgument(
                "use_language",
                default_value="False",
                choices=["True", "False"],
            ),
            DeclareLaunchArgument(
                "use_speech",
                default_value="False",
                choices=["True", "False"],
            ),
            DeclareLaunchArgument(
                "use_engagement",
                default_value="False",
                choices=["True", "False"],
            ),
            DeclareLaunchArgument(
                "require_engagement",
                default_value="False",
                choices=["True", "False"],
            ),
            DeclareLaunchArgument(
                "publish_debug_image",
                default_value="False",
                choices=["True", "False"],
            ),
            DeclareLaunchArgument(
                "use_scripted_visitor",
                default_value="True",
                choices=["True", "False"],
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(navigation_launch),
                launch_arguments={
                    "gzclient": LaunchConfiguration("gzclient"),
                    "nav2_params_file": LaunchConfiguration(
                        "nav2_params_file"
                    ),
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
                executable="language_node",
                name="language_node",
                output="screen",
                condition=IfCondition(LaunchConfiguration("use_language")),
                parameters=[{"use_sim_time": True}],
            ),
            Node(
                package="museum_assistant",
                executable="speech_to_text_node",
                name="speech_to_text_node",
                output="screen",
                condition=IfCondition(LaunchConfiguration("use_speech")),
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
            Node(
                package="museum_assistant",
                executable="visitor_session_node",
                name="visitor_session_node",
                output="screen",
                parameters=[
                    {
                        "use_sim_time": True,
                        "require_engagement": LaunchConfiguration(
                            "require_engagement"
                        ),
                    }
                ],
            ),
            Node(
                package="museum_assistant",
                executable="engagement_node",
                name="engagement_node",
                output="screen",
                condition=IfCondition(LaunchConfiguration("use_engagement")),
                parameters=[
                    {
                        "use_sim_time": True,
                        "publish_debug_image": LaunchConfiguration(
                            "publish_debug_image"
                        ),
                    }
                ],
            ),
            Node(
                package="museum_assistant",
                executable="scripted_visitor_node",
                name="scripted_visitor_node",
                output="screen",
                condition=IfCondition(LaunchConfiguration("use_scripted_visitor")),
                parameters=[{"use_sim_time": True}],
            ),
            Node(
                package="museum_assistant",
                executable="simulated_people_node",
                name="simulated_people_node",
                output="screen",
                condition=IfCondition(LaunchConfiguration("publish_people")),
                parameters=[{"use_sim_time": True}],
            ),
        ]
    )
