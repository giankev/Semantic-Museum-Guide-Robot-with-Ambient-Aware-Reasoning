from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    nav2_launch = PathJoinSubstitution(
        [FindPackageShare("nav2_bringup"), "launch", "bringup_launch.py"]
    )
    params_file = PathJoinSubstitution(
        [
            FindPackageShare("museum_assistant"),
            "config",
            "nav2_museum_social.yaml",
        ]
    )
    map_file = PathJoinSubstitution(
        [FindPackageShare("museum_assistant"), "maps", "museum_map.yaml"]
    )

    return LaunchDescription(
        [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(nav2_launch),
                launch_arguments={
                    "map": map_file,
                    "use_sim_time": "true",
                    "params_file": params_file,
                    "autostart": "true",
                    "use_composition": "False",
                    "slam": "False",
                }.items(),
            ),
        ]
    )
