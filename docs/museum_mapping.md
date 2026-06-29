# Museum Mapping With SLAM Toolbox

Milestone 8 adds a minimal SLAM Toolbox setup for creating a 2D occupancy map of the custom museum world. The saved map will later become the known map used by Nav2.

This milestone is mapping only. It does not add Nav2, autonomous navigation, LLM behavior, or vision.

## Interfaces

The current TIAGo Gazebo baseline exposes the required mapping interfaces:

- laser scan: `/scan_raw`
- odometry: `/mobile_base_controller/odom`
- transforms: `/tf` and `/tf_static`

`museum_slam.launch.py` launches `slam_toolbox` in online async mapping mode and remaps the node's `scan` input to `/scan_raw`.

The SLAM config uses:

- `map_frame: map`
- `odom_frame: odom`
- `base_frame: base_footprint`
- mapping mode
- simulated time

If runtime TF inspection shows that TIAGo only publishes `base_link` for the SLAM base frame, update `base_frame` in `config/slam_toolbox_museum.yaml` from `base_footprint` to `base_link`.

## Workflow

Build and source the workspace in the Docker container:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant
source install/setup.bash
```

Terminal 1, launch TIAGo in the museum world:

```bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

Terminal 2, launch SLAM Toolbox:

```bash
cd /root/exchange/exchange/museum_ws
source install/setup.bash
ros2 launch museum_assistant museum_slam.launch.py
```

Terminal 3, teleoperate TIAGo while mapping:

```bash
cd /root/exchange/exchange/museum_ws
source install/setup.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/mobile_base_controller/cmd_vel_unstamped
```

Drive slowly through the entrance, corridor, exhibition rooms, kids hall, temporary exhibition area, and exit. Avoid fast rotations; a slow, steady scan helps produce a cleaner occupancy map.

## Save The Map

After exploring the museum, save the map into the package `maps/` directory:

```bash
mkdir -p /root/exchange/exchange/museum_ws/src/museum_assistant/maps
ros2 run nav2_map_server map_saver_cli -f /root/exchange/exchange/museum_ws/src/museum_assistant/maps/museum_map
```

Expected output files:

```text
exchange/museum_ws/src/museum_assistant/maps/museum_map.yaml
exchange/museum_ws/src/museum_assistant/maps/museum_map.pgm
```

Do not commit a generated map until it has been inspected and confirmed useful.

## Later Nav2 Use

The generated `museum_map.yaml` and `museum_map.pgm` will be used in a later milestone as the known map for Nav2 localization and navigation. The semantic map already contains placeholder `nav_pose` values for rooms; after a good map exists, those poses can be checked and adjusted against the saved occupancy map.

## Current Limitations

- Mapping only; no autonomous navigation.
- No Nav2 bringup or localization yet.
- No automatic map quality validation.
- No semantic graph changes are made by this milestone.
