# Semantic Map Milestone

This milestone implements the first functional semantic predicate layer for the TIAGo museum guide project.

In the course notation `SM = <R, M, P>`, Milestone 2 documented the ROS2/Gazebo interfaces that support the reference and geometric/sensor layers `R` and `M`. This milestone starts `P`: rooms, artworks, roles, simulated room sensors, semantic relations, and deterministic recommendation rules.

Build and run inside the Docker container:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant
source install/setup.bash
ros2 run museum_assistant semantic_graph_node
ros2 run museum_assistant museum_query --style impressionism --avoid-crowd
ros2 run museum_assistant museum_query --child-friendly
ros2 launch museum_assistant semantic_graph.launch.py
```

This milestone does not include Nav2, LLM planning, vision, or live ambient sensor updates yet. The graph is loaded from YAML and queried deterministically.
