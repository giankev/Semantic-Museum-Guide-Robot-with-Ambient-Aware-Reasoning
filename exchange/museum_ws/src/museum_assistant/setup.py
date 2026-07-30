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
        (
            f"share/{package_name}/maps",
            ["maps/.gitkeep"]
            + glob("maps/*.yaml")
            + glob("maps/*.pgm")
            + glob("maps/*.png"),
        ),
        (f"share/{package_name}/worlds", glob("worlds/*.world")),
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
            (
                "visitor_session_node = "
                "museum_assistant.visitor_session_node:main"
            ),
            (
                "user_request_simulator = "
                "museum_assistant.user_request_simulator_node:main"
            ),
            "send_nav_goal = museum_assistant.send_nav_goal:main",
            "capture_nav_pose = museum_assistant.capture_nav_pose:main",
            "museum_query = museum_assistant.semantic_query_cli:main",
        ],
    },
)
