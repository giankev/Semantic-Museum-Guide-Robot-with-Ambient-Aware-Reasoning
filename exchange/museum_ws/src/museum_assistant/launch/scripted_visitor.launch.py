from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="scripted_visitor_node",
                name="scripted_visitor_node",
                output="screen",
                parameters=[
                    {
                        "use_sim_time": True,
                        "visitor_model_name": "visitor_marker",
                        "robot_model_name": "tiago",
                        "follow_distance": 1.5,
                        "follow_speed": 0.5,
                        "catchup_speed": 0.8,
                        "lag_after_seconds": 5.0,
                        "update_rate": 5.0,
                    }
                ],
            ),
        ]
    )
