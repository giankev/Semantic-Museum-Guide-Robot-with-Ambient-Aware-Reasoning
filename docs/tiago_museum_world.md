# TIAGo In The Museum World

Milestone 7 connects the validated TIAGo Gazebo baseline to the lightweight museum world created for the semantic museum guide demo.

The museum world represents the same semantic rooms defined in `exchange/museum_ws/src/museum_assistant/config/semantic_map.yaml`:

- `entrance`
- `main_corridor`
- `impressionism_hall`
- `ancient_art_hall`
- `kids_hall`
- `temporary_exhibition`
- `exit`

The room floor zones are placed near the current placeholder `nav_pose` coordinates. The entrance is centered near `(0, 0)`, which matches the default TIAGo spawn position used by the public simulation launch.

## Launch

Build and source the package inside the Docker container:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant
source install/setup.bash
```

Launch TIAGo with the museum world:

```bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

This launch file wraps `tiago_gazebo.launch.py` and uses only arguments listed in `docs/raw/tiago_gazebo_launch_args.txt`, including `world_name`, `is_public_sim`, `navigation`, `advanced_navigation`, `slam`, `gazebo_version`, `gzclient`, and `rviz`.

The captured TIAGo launch arguments do not expose explicit `x`, `y`, or `yaw` spawn-pose parameters. For this milestone, TIAGo uses the default spawn pose, and the museum entrance is designed around that pose.

## Manual Teleop Test

From a second terminal on the host, enter the same running container:

```bash
docker exec -it museum_tiago bash
```

Then run:

```bash
cd /root/exchange/exchange/museum_ws
source install/setup.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/mobile_base_controller/cmd_vel_unstamped
```

Expected result:

- Gazebo opens.
- The custom museum world is visible.
- TIAGo is spawned near the entrance/default safe area.
- TIAGo can be moved manually with keyboard teleoperation.

## Current Limitations

- Nav2 is not enabled in this launch.
- SLAM is not enabled in this launch.
- The robot is not navigating autonomously.
- No LLM or vision functionality is connected to this launch.
- If a more precise spawn pose is needed later, the next milestone should inspect the lower-level TIAGo spawn mechanism because the public launch arguments do not expose spawn coordinates.
