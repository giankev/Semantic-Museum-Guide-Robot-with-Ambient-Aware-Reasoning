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
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Museum Robotics Team",
    maintainer_email="museum@example.com",
    description="Minimal semantic and ambient reasoning nodes for a TIAGo museum guide robot.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "semantic_graph_node = museum_assistant.semantic_graph_node:main",
            "sensor_simulator_node = museum_assistant.sensor_simulator_node:main",
            "cli_node = museum_assistant.cli_node:main",
        ],
    },
)
