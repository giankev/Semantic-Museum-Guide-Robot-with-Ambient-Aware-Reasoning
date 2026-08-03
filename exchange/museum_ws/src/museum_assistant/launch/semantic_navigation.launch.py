from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="semantic_navigation_node",
                name="semantic_navigation_node",
                output="screen",
                parameters=[
                    {
                        "use_sim_time": True,
                        "resume_distance": 2.0,
                        "wait_distance": 3.0,
                        "lost_distance": 8.0,
                        "arrival_distance": 2.5,
                        "wait_delay": 3.0,
                        "absence_timeout": 3.0,
                    }
                ],
            ),
        ]
    )
