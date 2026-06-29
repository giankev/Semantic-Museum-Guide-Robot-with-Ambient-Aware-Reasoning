# Semantic Museum Guide Robot with Ambient-Aware Reasoning

This repository contains a focused ROS2 Humble project for a semantic-aware museum guide robot. The target platform is a simulated PAL Robotics TIAGo robot in Gazebo, using Nav2 on a known museum map, a semantic graph of rooms and artworks, simulated ambient sensors, LLM-based reasoning, and later a lightweight vision node.

The project is intentionally scoped to TIAGo, Gazebo, Nav2, and ROS2 Humble. Booster T1, Circus, SimBridge, Webots, MuJoCo, Pixi, Booster SDK, and Booster-specific runtime assets have been removed so the repository stays aligned with the museum guide demo.

## Why TIAGo/Gazebo/Nav2 Only

TIAGo is a service robot that matches the museum guide scenario: indoor navigation, human-facing interaction, camera-based perception, and ROS2 integration. Gazebo and Nav2 provide the shortest path to a reproducible navigation stack with a known map and simulated sensors. Keeping one simulator and one robot avoids mixing unrelated locomotion, bridge, and supervisor systems.

## Current Structure

```text
dockerfiles/
  Dockerfile.tiago_museum        # ROS2 Humble + TIAGo public simulation workspace
docs/
  setup_tiago_museum.md          # Detailed setup and first-test instructions
exchange/
  museum_ws/
    src/
      museum_assistant/          # Minimal ROS2 Python package for semantic/ambient nodes
start_museum_tiago.sh            # Docker run helper for X11 Gazebo/RViz sessions
README.md
```

## Removed

The old mixed simulation stack was removed, including `circus/`, `simbridge/`, Booster T1 assets, `booster_robotics_sdk`, `booster_robotics_sdk_ros2`, `LocoApiPackage`, Booster supervisor/config files, old Booster entrypoints, Webots assets, Pixi files, and the previous combined Dockerfile.

## Build The Docker Image

Build all ROS2, Gazebo, Nav2, SLAM Toolbox, Python utility, and TIAGo public workspace dependencies inside the image:

```bash
docker build -f dockerfiles/Dockerfile.tiago_museum -t museum-tiago:humble .
```

## Run The Container

Use the helper script from the repository root:

```bash
chmod +x start_museum_tiago.sh
./start_museum_tiago.sh
```

The script runs `museum-tiago:humble` with host networking, X11 display access for Gazebo/RViz, optional NVIDIA GPU support when `nvidia-smi` is available, and mounts this repository at `/root/exchange`.

Equivalent manual command:

```bash
docker run --rm -it --net=host \
  -e DISPLAY="$DISPLAY" \
  -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v "$PWD:/root/exchange" \
  -w /root/exchange \
  museum-tiago:humble \
  bash
```

## Build The Museum ROS2 Workspace

Inside the container:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install
source install/setup.bash
```

Run the minimal museum assistant nodes:

```bash
ros2 launch museum_assistant museum_assistant.launch.py
```

The semantic graph node loads `semantic_map.yaml`, the ambient simulator publishes JSON status messages on `/museum/ambient_status`, and the CLI node prints the current placeholder instructions.

## First TIAGo Gazebo Test

Inside the container, the ROS2 and TIAGo public workspaces are sourced automatically from `/root/.bashrc`. Start a basic TIAGo public simulation with:

```bash
ros2 launch tiago_gazebo tiago_gazebo.launch.py is_public_sim:=True
```

Use this first to confirm Gazebo opens and TIAGo spawns correctly before adding museum maps, Nav2 goals, or reasoning logic.

## Roadmap

1. Add a museum Gazebo world and known map for Nav2 localization.
2. Expand `semantic_map.yaml` into a graph of rooms, artworks, styles, constraints, and Nav2 poses.
3. Connect ambient sensor topics to graph updates for crowd, noise, closures, and route status.
4. Add deterministic reasoning over semantic graph constraints and Nav2 goal selection.
5. Add controlled LLM parsing from visitor requests to structured intent JSON.
6. Add a lightweight vision node for role/status cues, such as staff badge or guide marker detection.
7. Build demo scenarios where TIAGo recommends, explains, and navigates to suitable exhibits.
