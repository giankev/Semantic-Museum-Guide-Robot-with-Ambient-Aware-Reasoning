from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess


def generate_launch_description():
    package_share = get_package_share_directory("museum_assistant")
    world_path = str(Path(package_share) / "worlds" / "museum.world")

    return LaunchDescription([
        ExecuteProcess(
            cmd=["gazebo", "--verbose", world_path],
            output="screen",
        )
    ])
