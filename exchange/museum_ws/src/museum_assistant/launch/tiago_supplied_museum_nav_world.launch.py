from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def supplied_museum_nav_world_path() -> str:
    package_share = Path(get_package_share_directory("museum_assistant"))
    return str(
        package_share / "worlds" / "supplied_museum" / "museum_nav.world"
    )


def generate_launch_description():
    tiago_gazebo_launch = PathJoinSubstitution(
        [FindPackageShare("tiago_gazebo"), "launch", "tiago_gazebo.launch.py"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "gzclient",
                default_value="False",
                choices=["True", "False"],
                description="Start the Gazebo Classic graphical client.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(tiago_gazebo_launch),
                launch_arguments={
                    "world_name": supplied_museum_nav_world_path(),
                    "is_public_sim": "True",
                    "navigation": "False",
                    "advanced_navigation": "False",
                    "slam": "False",
                    "moveit": "False",
                    "tuck_arm": "False",
                    "gazebo_version": "classic",
                    "gzclient": LaunchConfiguration("gzclient"),
                    "rviz": "False",
                }.items(),
            ),
        ]
    )
