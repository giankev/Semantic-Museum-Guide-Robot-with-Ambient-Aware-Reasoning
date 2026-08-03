# Museum Gazebo World Baseline

This page records the historical world-only milestone that added a lightweight Gazebo Classic museum scene. The current repository also includes `tiago_museum_world.launch.py`, a saved map, and separate SLAM/Nav2 launch files.

The world is installed as:

```text
museum_assistant/worlds/museum.world
```

It represents the rooms from `config/semantic_map.yaml` with simple colored floor zones placed near the current placeholder `nav_pose` coordinates:

- `entrance`
- `main_corridor`
- `impressionism_hall`
- `ancient_art_hall`
- `kids_hall`
- `temporary_exhibition`
- `exit`

The scene uses only basic Gazebo geometry: boxes for walls, floor zones, partitions, and artwork plaques; cylinders and spheres for simple visitor, guide, and staff markers. No external meshes, downloaded assets, or large model dependencies are required.

Build and open the world inside the Docker container:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant
source install/setup.bash
ros2 launch museum_assistant museum_world.launch.py
```

For the final video, this world can show the project environment while the semantic graph, ambient sensor updates, and reasoning responses are demonstrated in ROS2 terminals.

Limitations of `museum_world.launch.py` and the world asset:

- This world-only launch does not spawn TIAGo or start Nav2.
- TIAGo is spawned by `tiago_museum_world.launch.py`.
- Nav2 localization is started separately by `museum_navigation.launch.py`.
- The world contains static person-shaped visual markers, not actors, tracked people, or engagement/session data.
- The world is intentionally simple and functional, not a polished museum model.
