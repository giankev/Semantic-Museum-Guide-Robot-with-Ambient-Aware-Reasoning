# Semantic World-Model Baseline

This page records the historical semantic-map milestone that implemented the first functional semantic predicate layer. The current repository has since added live scripted ambient updates, structured deterministic reasoning, a museum world, a saved map, and a separate Nav2 baseline.

In the course notation `SM = <R, M, P>`, the earlier ROS 2/Gazebo interface inventory supports the reference and geometric/sensor layers `R` and `M`. This semantic baseline starts `P`: rooms, artworks, roles, simulated room sensors, semantic relations, and deterministic recommendation rules.

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

At the time of this milestone, the graph was loaded from YAML and queried deterministically without live updates. The current package now updates room ambient state in memory through `/museum/ambient_state`, but it still has no LLM, vision, session/task knowledge, persistent state store, or connection from reasoning to Nav2.

## Navigation Pose Calibration

Room and artwork `nav_pose` values should be calibrated from `/amcl_pose` on the saved museum map, not guessed from the Gazebo layout. After TIAGo is localized with Nav2 active, drive it to a safe stopping point and run:

```bash
ros2 run museum_assistant capture_nav_pose --name <room_or_artwork_id>
```

Review the printed YAML snippet before copying its `x`, `y`, and `yaw` values into the matching `nav_pose` entry in `config/semantic_map.yaml`, or before storing it in a future navigation-goals file. A pose being present in YAML does not prove that it is calibrated or currently free in the Nav2 costmaps.
