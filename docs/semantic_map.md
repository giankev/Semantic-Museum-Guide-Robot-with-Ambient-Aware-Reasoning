# Dynamic Semantic Scene Graph

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

## Three distinct layers

The project deliberately separates three representations:

- the occupancy map is geometric data used by AMCL, Nav2, and obstacle
  avoidance;
- `MuseumSemanticGraph` is the NetworkX scene graph of rooms, artworks,
  sensors, roles, concepts, semantic relations, and current room attributes;
- `DeterministicReasoner` applies validated task constraints to that graph and
  emits only a fixed skill such as `navigate_to` or `ask_clarification`.

The scene graph does not replace Nav2 or the supplied route runner. In
particular, `connected_to` is a report/debug topology relation, not a geometric
path planner.

Artwork selection traverses `artwork --located_in--> room` edges. Room
availability, crowd, noise, child suitability, and accessibility are read from
ROOM node attributes. `/museum/ambient_state` updates `status`, `crowd_level`,
or `noise_level` in memory; updates are validated, immediately visible to the
next decision, and never written back to YAML.

`MuseumSemanticGraph.neighbors()` provides a small relation query, while
`snapshot()` returns compact JSON-safe `nodes` and `edges` collections. The
reasoning node publishes that snapshot on `/museum/scene_graph` at startup and
after every valid ambient update.

Run the ROS-independent functional benchmark without Gazebo, Nav2, or APIs:

```bash
python3 /root/exchange/scripts/benchmark_scene_graph_reasoning.py
```

## Navigation Pose Calibration

Room and artwork `nav_pose` values should be calibrated from `/amcl_pose` on the saved museum map, not guessed from the Gazebo layout. After TIAGo is localized with Nav2 active, drive it to a safe stopping point and run:

```bash
ros2 run museum_assistant capture_nav_pose --name <room_or_artwork_id>
```

Review the printed YAML snippet before copying its `x`, `y`, and `yaw` values into the matching `nav_pose` entry in `config/semantic_map.yaml`, or before storing it in a future navigation-goals file. A pose being present in YAML does not prove that it is calibrated or currently free in the Nav2 costmaps.
