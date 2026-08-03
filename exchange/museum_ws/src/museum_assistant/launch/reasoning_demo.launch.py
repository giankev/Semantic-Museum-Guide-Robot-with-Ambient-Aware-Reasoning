from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="museum_assistant",
                executable="reasoning_node",
                name="reasoning_node",
                output="screen",
            ),
            Node(
                package="museum_assistant",
                executable="ambient_sensor_simulator",
                name="ambient_sensor_simulator_node",
                output="screen",
            ),
            Node(
                package="museum_assistant",
                executable="user_request_simulator",
                name="user_request_simulator_node",
                output="screen",
            ),
        ]
    )
