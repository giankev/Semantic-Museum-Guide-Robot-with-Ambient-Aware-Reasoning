from glob import glob
from setuptools import setup

package_name = "museum_assistant"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/behavior_trees", glob("behavior_trees/*.xml")),
        (
            f"share/{package_name}/maps",
            ["maps/.gitkeep"]
            + glob("maps/*.yaml")
            + glob("maps/*.pgm")
            + glob("maps/*.png"),
        ),
        (f"share/{package_name}/worlds", glob("worlds/*.world")),
        (
            f"share/{package_name}/worlds/supplied_museum",
            glob("worlds/supplied_museum/*"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Museum Robotics Team",
    maintainer_email="museum@example.com",
    description=(
        "Semantic world model, deterministic reasoning, simulation assets, "
        "and Nav2 helpers for a TIAGo museum guide robot."
    ),
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "semantic_graph_node = museum_assistant.semantic_graph_node:main",
            (
                "ambient_sensor_simulator = "
                "museum_assistant.ambient_sensor_simulator_node:main"
            ),
            "reasoning_node = museum_assistant.reasoning_node:main",
            "language_node = museum_assistant.language_node:main",
            (
                "speech_to_text_node = "
                "museum_assistant.speech_to_text_node:main"
            ),
            (
                "semantic_navigation_node = "
                "museum_assistant.semantic_navigation_node:main"
            ),
            (
                "semantic_route_dispatcher = "
                "museum_assistant.semantic_route_dispatcher_node:main"
            ),
            (
                "visitor_session_node = "
                "museum_assistant.visitor_session_node:main"
            ),
            (
                "scripted_visitor_node = "
                "museum_assistant.scripted_visitor_node:main"
            ),
            (
                "simulated_people_node = "
                "museum_assistant.simulated_people_node:main"
            ),
            (
                "social_people_bridge_node = "
                "museum_assistant.social_people_bridge_node:main"
            ),
            (
                "user_request_simulator = "
                "museum_assistant.user_request_simulator_node:main"
            ),
            "send_nav_goal = museum_assistant.send_nav_goal:main",
            "capture_nav_pose = museum_assistant.capture_nav_pose:main",
            (
                "simulation_ground_truth_odom = "
                "museum_assistant.simulation_ground_truth_odom_node:main"
            ),
            (
                "supplied_museum_route_runner = "
                "museum_assistant.supplied_museum_route_runner:main"
            ),
            (
                "supplied_museum_route_runner_node = "
                "museum_assistant.supplied_museum_route_runner:topic_main"
            ),
            "museum_query = museum_assistant.semantic_query_cli:main",
        ],
    },
)
