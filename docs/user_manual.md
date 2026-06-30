# User Manual — Semantic Museum Guide Robot

## Short Project Overview

This project integrates a TIAGo robot in Gazebo with a custom museum world, semantic map and reasoning code, simulated ambient sensors, SLAM mapping, and Nav2 known-map navigation. The current system supports deterministic semantic and ambient-aware demos, map creation, and manual Nav2 goal testing. Future milestones will connect semantic recommendations directly to navigation execution and add controlled LLM parsing plus lightweight role-aware perception.

## Prerequisites

- Ubuntu host machine with Docker available.
- Docker image already built as `museum-tiago:humble`.
- Container started through `./start_museum_tiago.sh`.
- Commands are run either on the host or inside the Docker container, as noted below.
- Every new terminal inside the container should source the ROS workspaces before running ROS2 commands:

```bash
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
cd /root/exchange/exchange/museum_ws
source install/setup.bash
```

## Important Paths

Host repo:

```bash
~/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
```

Container mounted repo:

```bash
/root/exchange
```

ROS2 workspace inside container:

```bash
/root/exchange/exchange/museum_ws
```

Main ROS2 package:

```bash
/root/exchange/exchange/museum_ws/src/museum_assistant
```

## Start Docker Container

From a host terminal:

```bash
cd ~/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
./start_museum_tiago.sh
```

This starts the `museum-tiago:humble` image and opens an interactive shell in the running container named:

```bash
museum_tiago
```

## Build The ROS2 Package

Inside the container:

```bash
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant
source install/setup.bash
```

Compact form from a new host terminal:

```bash
docker exec -it museum_tiago bash -lc "source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && colcon build --symlink-install --packages-select museum_assistant && source install/setup.bash"
```

## Launch Custom Museum World Only

Inside a sourced container terminal, this launches Gazebo with the custom museum world but without TIAGo:

```bash
ros2 launch museum_assistant museum_world.launch.py
```

## Launch TIAGo In The Museum World

Terminal 1, inside the container:

```bash
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
cd /root/exchange/exchange/museum_ws
source install/setup.bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

This opens Gazebo with TIAGo inside the custom museum world.

## Manual Teleoperation

Terminal 2, from the host:

```bash
docker exec -it museum_tiago bash -lc "source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/mobile_base_controller/cmd_vel_unstamped"
```

Keep the teleop terminal focused, use the keys shown by `teleop_twist_keyboard`, and stop with `CTRL+C`.

## Semantic Graph Demo

Inside a sourced container terminal:

```bash
ros2 launch museum_assistant semantic_graph.launch.py
```

CLI examples:

```bash
ros2 run museum_assistant museum_query --style impressionism --avoid-crowd
ros2 run museum_assistant museum_query --child-friendly
ros2 run museum_assistant museum_query --wheelchair-accessible
```

This tests semantic room and artwork selection without robot movement.

## Ambient Reasoning Demo

Inside a sourced container terminal:

```bash
ros2 launch museum_assistant ambient_reasoning.launch.py
```

This publishes simulated room crowd, noise, and status updates on `/museum/ambient_state`, updates the semantic graph dynamically, and demonstrates ambient-aware recommendation behavior.

## Deterministic Reasoning Demo

Inside a sourced container terminal:

```bash
ros2 launch museum_assistant reasoning_demo.launch.py
```

Main topics:

- `/museum/user_request`
- `/museum/ambient_state`
- `/museum/assistant_response`

Inspect assistant responses:

```bash
ros2 topic echo /museum/assistant_response
```

This demo uses structured JSON requests and deterministic reasoning. It does not execute robot navigation.

## SLAM Mapping Workflow

Use this workflow to create or update the occupancy map used later by Nav2.

Terminal 1, inside the container, launch TIAGo in the museum:

```bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

Terminal 2, from the host, launch SLAM:

```bash
docker exec -it museum_tiago bash -lc "source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && ros2 launch museum_assistant museum_slam.launch.py"
```

Terminal 3, from the host, teleoperate slowly while mapping:

```bash
docker exec -it museum_tiago bash -lc "source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/mobile_base_controller/cmd_vel_unstamped"
```

Check that `/map` is publishing:

```bash
docker exec -it museum_tiago bash -lc "source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && ros2 topic echo /map --once"
```

Save the map:

```bash
docker exec -it museum_tiago bash -lc "source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && mkdir -p /root/exchange/exchange/museum_ws/src/museum_assistant/maps && ros2 run nav2_map_server map_saver_cli -f /root/exchange/exchange/museum_ws/src/museum_assistant/maps/museum_map"
```

Expected files:

```bash
exchange/museum_ws/src/museum_assistant/maps/museum_map.yaml
exchange/museum_ws/src/museum_assistant/maps/museum_map.pgm
```

## Known-Map Nav2 Navigation

Terminal 1, inside the container, launch TIAGo in the museum:

```bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

Terminal 2, from the host, launch Nav2:

```bash
docker exec -it museum_tiago bash -lc "source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && ros2 launch museum_assistant museum_navigation.launch.py"
```

Terminal 3, from the host, check lifecycle states:

```bash
docker exec -it museum_tiago bash -lc 'source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && for n in /map_server /amcl /planner_server /controller_server /bt_navigator /behavior_server; do echo "--- $n"; ros2 lifecycle get $n 2>/dev/null || true; done'
```

Expected result for the main lifecycle nodes:

```text
active [3]
```

## Send Nav2 Goals

Coordinate mode:

```bash
docker exec -it museum_tiago bash -lc "source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && ros2 run museum_assistant send_nav_goal --x 1.0 --y 0.0 --yaw 0.0"
```

Random coordinates may fail if the point is inside occupied, unknown, or inflated costmap space. Prefer goals chosen from free space in RViz or from calibrated semantic poses.

Named goal mode is not available in the current package. There is no `nav_goals.yaml` file and `send_nav_goal` currently accepts coordinate arguments only.

## Capture Semantic Navigation Poses

Use teleop to place the robot at a safe pose, then run:

```bash
docker exec -it museum_tiago bash -lc "source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && ros2 run museum_assistant capture_nav_pose --name impressionism_hall"
```

The command reads `/amcl_pose` and prints a YAML snippet. Review the output, then copy the `x`, `y`, and `yaw` values into the matching semantic or navigation-goal configuration.

## Generate Semantic Nav Goals

The current package does not include a `generate_nav_goals` executable. This is a future helper for generating or proposing safe navigation goals from the saved map and semantic targets. Until then, use `capture_nav_pose` and manually review poses before adding them to configuration.

## Useful Debug Commands

Inside a sourced container terminal:

```bash
ros2 topic list | grep -E "scan|odom|tf|map|amcl|cmd_vel|costmap"
```

```bash
ros2 topic info /scan_raw
ros2 topic info /mobile_base_controller/odom
ros2 topic info /cmd_vel
ros2 topic info /mobile_base_controller/cmd_vel_unstamped
```

```bash
ros2 node list
ros2 action list | grep navigate
```

```bash
ros2 topic echo /amcl_pose --once
```

## Troubleshooting

`Package museum_assistant not found`

- Run `cd /root/exchange/exchange/museum_ws`.
- Run `source install/setup.bash`.
- Rebuild with `colcon build --symlink-install --packages-select museum_assistant` if needed.

`ros2: command not found`

- Source `/opt/ros/humble/setup.bash`.
- Source `/root/tiago_public_ws/install/setup.bash`.

`No such container: museum_tiago`

- Start the container with `./start_museum_tiago.sh` from the host repo root.

`Goal rejected`

- Check Nav2 lifecycle states.
- Confirm `/bt_navigator` is `active [3]`.

`Goal accepted but aborted`

- The goal may be in occupied, unknown, or inflated space.
- Choose a safer goal and inspect costmaps.
- Use calibrated semantic navigation poses instead of random coordinates.

`bt_navigator inactive`

- Check the BT XML path in `config/nav2_museum.yaml`.
- The expected file is `/opt/ros/humble/share/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml`.

Gazebo graphics issues:

- Close heavy applications.
- Kill stale Gazebo processes if needed:

```bash
killall gzserver gzclient gazebo 2>/dev/null || true
```

## Current Limitations

- Nav2 known-map navigation works but may still need tuning.
- Not all arbitrary map coordinates are valid navigation goals.
- Semantic reasoning is not yet fully connected to Nav2 unless a navigation executor milestone is implemented.
- The LLM parser is future work.
- Vision and HRI role-awareness extensions are future work.

## Final Demo Sequence

Suggested order:

1. Launch TIAGo in the museum world.
2. Show a semantic query with `museum_query`.
3. Show ambient reasoning with `ambient_reasoning.launch.py`.
4. Launch Nav2 with `museum_navigation.launch.py`.
5. Send a calibrated coordinate goal with `send_nav_goal`, or a semantic/named goal after that milestone is implemented.
6. Show TIAGo moving in Gazebo.
7. Explain current limitations and the planned semantic-to-navigation connection.
