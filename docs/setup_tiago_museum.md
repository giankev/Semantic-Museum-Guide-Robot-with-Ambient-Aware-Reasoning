# TIAGo Museum Setup

This guide sets up the focused TIAGo/Gazebo/Nav2 museum project. All ROS2 and TIAGo dependencies are installed inside Docker; the host only needs Docker, X11 display access, and optionally NVIDIA container support.

## Host Requirements

- Ubuntu/Linux host with Docker installed
- X11 session or X11 forwarding available through `$DISPLAY`
- Optional: NVIDIA driver and NVIDIA Container Toolkit for GPU-accelerated Gazebo

No Booster SDK, Circus, SimBridge, Webots, MuJoCo, Pixi, or host ROS2 installation is required.

## Build The Image

From the repository root:

```bash
docker build -f dockerfiles/Dockerfile.tiago_museum -t museum-tiago:humble .
```

The Dockerfile starts from `ros:humble`, installs the minimal ROS2/Gazebo/Nav2/SLAM Toolbox packages, installs Python reasoning utilities, imports the PAL Robotics TIAGo public workspace from:

```text
https://raw.githubusercontent.com/pal-robotics/tiago_tutorials/humble-devel/tiago_public.repos
```

Then it resolves dependencies with `rosdep` and builds `/root/tiago_public_ws`.

## Start The Container

From the repository root:

```bash
chmod +x start_museum_tiago.sh
./start_museum_tiago.sh
```

The container starts in `/root/exchange`, which is the mounted repository. It uses host networking and mounts `/tmp/.X11-unix` so Gazebo and RViz can open on the host display. The script does not mount `/var/run/docker.sock`.

If your host blocks X11 clients, run:

```bash
xhost +local:docker
```

Then start the container again.

## Verify TIAGo Gazebo

Inside the container:

```bash
ros2 launch tiago_gazebo tiago_gazebo.launch.py is_public_sim:=True
```

Expected result: Gazebo opens and spawns the TIAGo public simulation. This verifies the Docker image, X11 display, ROS2 environment, and TIAGo workspace.

## Build The Museum Workspace

Open a new container shell or stop Gazebo, then run:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install
source install/setup.bash
```

Launch the starter museum nodes:

```bash
ros2 launch museum_assistant museum_assistant.launch.py
```

Useful checks:

```bash
ros2 topic echo /museum/ambient_status
ros2 run museum_assistant semantic_graph_node
ros2 run museum_assistant sensor_simulator_node
ros2 run museum_assistant cli_node
```

## What The Starter Nodes Do

- `semantic_graph_node` loads `config/semantic_map.yaml` and logs the available rooms and artworks.
- `sensor_simulator_node` publishes simulated crowd, noise, and room status data as JSON on `/museum/ambient_status`.
- `cli_node` prints placeholder instructions for the later visitor command interface.

## Next Development Steps

1. Create a museum Gazebo world and save a known map.
2. Add Nav2 localization and waypoint goals for each semantic room.
3. Replace placeholder ambient samples with configurable simulated sensors.
4. Add graph reasoning with NetworkX.
5. Add controlled LLM request parsing.
6. Add the lightweight vision node after the semantic and navigation loop is stable.
