from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    museum_world = PathJoinSubstitution(
        [FindPackageShare("museum_assistant"), "worlds", "museum.world"]
    )
    tiago_gazebo_launch = PathJoinSubstitution(
        [FindPackageShare("tiago_gazebo"), "launch", "tiago_gazebo.launch.py"]
    )

    return LaunchDescription(
        [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(tiago_gazebo_launch),
                launch_arguments={
                    "world_name": museum_world,
                    "is_public_sim": "True",
                    "navigation": "False",
                    "advanced_navigation": "False",
                    "slam": "False",
                    "gazebo_version": "classic",
                    "gzclient": "True",
                    "rviz": "False",
                }.items(),
            ),
        ]
    )
