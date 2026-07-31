from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="visitor_session_node",
                name="visitor_session_node",
                output="screen",
                parameters=[
                    {
                        "use_sim_time": True,
                        "visitor_model_name": "visitor_marker",
                        "robot_model_name": "tiago",
                    }
                ],
            ),
        ]
    )
