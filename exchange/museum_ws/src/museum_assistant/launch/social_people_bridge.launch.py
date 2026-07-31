from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="social_people_bridge_node",
                name="social_people_bridge_node",
                output="screen",
                parameters=[{"use_sim_time": True}],
            ),
        ]
    )
