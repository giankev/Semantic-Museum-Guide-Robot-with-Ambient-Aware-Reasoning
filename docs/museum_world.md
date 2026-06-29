# Museum Gazebo World

Milestone 6 adds a lightweight Gazebo Classic world for the visual museum demo scene.

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

Limitations:

- Nav2 is not integrated yet.
- TIAGo is not automatically spawned into this custom world yet.
- There is no automatic navigation or map localization in this milestone.
- The world is intentionally simple and functional, not a polished museum model.
