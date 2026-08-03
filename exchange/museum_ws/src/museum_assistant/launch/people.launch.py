from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="simulated_people_node",
                name="simulated_people_node",
                output="screen",
                parameters=[{"use_sim_time": True}],
            ),
        ]
    )
