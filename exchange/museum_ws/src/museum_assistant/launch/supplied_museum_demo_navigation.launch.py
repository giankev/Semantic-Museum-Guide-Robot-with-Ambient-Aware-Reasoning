"""Reproducible four-gallery supplied-museum navigation demo."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    museum_share = FindPackageShare("museum_assistant")
    world_launch = PathJoinSubstitution(
        [museum_share, "launch", "tiago_supplied_museum_ground_truth_odom.launch.py"]
    )
    nav2_launch = PathJoinSubstitution(
        [FindPackageShare("nav2_bringup"), "launch", "bringup_launch.py"]
    )
    map_file = PathJoinSubstitution(
        [museum_share, "maps", "supplied_museum_nav.yaml"]
    )
    params_file = LaunchConfiguration("nav2_params_file")

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(nav2_launch),
        launch_arguments={
            "map": map_file,
            "params_file": params_file,
            "use_sim_time": "true",
            "autostart": "true",
            "use_composition": "False",
            "slam": "False",
        }.items(),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "gzclient",
                default_value="False",
                choices=["True", "False"],
                description="Start the Gazebo Classic graphical client.",
            ),
            DeclareLaunchArgument(
                "nav2_params_file",
                default_value=PathJoinSubstitution(
                    [museum_share, "config", "nav2_supplied_demo.yaml"]
                ),
                description="Opt-in Nav2 parameter file; defaults to baseline.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(world_launch),
                launch_arguments={"gzclient": LaunchConfiguration("gzclient")}.items(),
            ),
            TimerAction(period=15.0, actions=[navigation]),
        ]
    )
