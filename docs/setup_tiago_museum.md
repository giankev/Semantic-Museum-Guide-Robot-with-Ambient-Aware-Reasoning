# TIAGo Museum Setup

This guide sets up the TIAGo/Gazebo/Nav2 museum project. ROS 2, TIAGo, Gazebo, Nav2, SLAM Toolbox, and Python reasoning dependencies stay inside Docker.

For demo commands after installation, continue with [the user manual](user_manual.md).

## Host Requirements

- Ubuntu/Linux host with Docker Engine
- X11 session or X11 forwarding through `$DISPLAY`
- Optional NVIDIA driver and NVIDIA Container Toolkit

No host ROS 2 installation is required. Booster SDK, Circus, SimBridge, Webots, MuJoCo, and Pixi are not used.

## Build The Image

From the repository root:

```bash
docker build -f dockerfiles/Dockerfile.tiago_museum -t museum-tiago:humble .
```

The Dockerfile:

- starts from `ros:humble`;
- installs Gazebo Classic ROS packages, Nav2, SLAM Toolbox, teleop, and lightweight Python dependencies;
- imports the public TIAGo Humble workspace from PAL Robotics;
- resolves the TIAGo workspace dependencies with `rosdep`;
- builds `/root/tiago_public_ws`.

## Start The Container

From the repository root:

```bash
./start_museum_tiago.sh
```

The script starts container `museum_tiago` with:

- host networking;
- the repository mounted at `/root/exchange`;
- X11 display access;
- optional NVIDIA GPU access when `nvidia-smi` is available;
- Cyclone DDS as the ROS middleware.

If the host blocks X11 clients:

```bash
xhost +local:docker
./start_museum_tiago.sh
```

## Build The Museum Package

Inside the container:

```bash
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant
source install/setup.bash
```

Every new container terminal must source the ROS 2, TIAGo, and museum workspaces before running package commands.

## Verify The Baseline

Launch TIAGo in the custom museum world:

```bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

In a second sourced terminal, test teleoperation:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard \
  --ros-args -r cmd_vel:=/mobile_base_controller/cmd_vel_unstamped
```

Expected baseline:

- Gazebo opens with the custom museum world.
- TIAGo spawns near the entrance.
- `/scan_raw`, `/mobile_base_controller/odom`, `/tf`, and `/tf_static` are available.
- Keyboard teleoperation moves the base.

## Verify The Semantic Package

Run a direct semantic query:

```bash
ros2 run museum_assistant museum_query --style impressionism --avoid-crowd
```

Run the deterministic request demo:

```bash
ros2 launch museum_assistant reasoning_demo.launch.py
```

The demo uses:

- `/museum/user_request`
- `/museum/ambient_state`
- `/museum/assistant_response`

There is no `museum_assistant.launch.py`, `sensor_simulator_node`, `cli_node`, or `/museum/ambient_status` interface in the current package.

## Verify Known-Map Navigation

Keep `tiago_museum_world.launch.py` running, then start Nav2 in another sourced terminal:

```bash
ros2 launch museum_assistant museum_navigation.launch.py
```

Check the principal lifecycle nodes:

```bash
ros2 lifecycle get /map_server
ros2 lifecycle get /amcl
ros2 lifecycle get /planner_server
ros2 lifecycle get /controller_server
ros2 lifecycle get /bt_navigator
ros2 lifecycle get /behavior_server
```

The validated baseline has these nodes active and accepts `/navigate_to_pose` goals, but some coordinates still require calibration or tuning. Use the goal-selection and troubleshooting workflow in [Known-Map Navigation With Nav2](museum_navigation.md).

## Current Scope

Implemented setup paths include the museum simulation, semantic and ambient demos, saved-map localization, Nav2 bringup, and manual goal helpers.

The following are not installed or started by this setup:

- person/engagement perception;
- visitor sessions;
- natural-language or speech processing;
- interaction/behavior execution;
- escort supervision;
- social navigation;
- role-aware vision.
