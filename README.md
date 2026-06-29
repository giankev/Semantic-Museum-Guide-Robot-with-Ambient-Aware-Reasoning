# Semantic Museum Guide Robot with Ambient-Aware Reasoning

## Project Overview

This project implements a TIAGo-based museum guide robot in simulation. The target system is a mobile service robot that can navigate through an indoor museum environment and support visitors through semantic, context-aware guidance.

The intended final system uses a known map, ROS2 Humble, Gazebo simulation, Nav2 navigation, a semantic graph of the museum, simulated ambient sensors, LLM-based reasoning, and later a lightweight vision module for role-aware interaction. The semantic layer will connect visitor requests to rooms, artworks, constraints, and navigation goals. Ambient sensing will provide dynamic context such as crowd level, room status, and environmental conditions. The vision module is planned for lightweight recognition of guide or staff cues, such as a badge or marker, without identifying individual people.

At the current stage, the repository provides the focused Docker environment, TIAGo Gazebo launch path, and a minimal ROS2 Python workspace for the future museum assistant nodes.

## Why TIAGo/Gazebo/Nav2

The original course stack contained multiple robots, simulators, and integration layers. This repository has been refactored to focus on the TIAGo/Gazebo/Nav2 track because it is the most suitable track for an indoor museum-guide scenario.

TIAGo is a service robot platform designed for human-centered indoor environments. Gazebo provides a practical simulation environment for testing robot behavior before introducing a custom museum world. Nav2 provides the ROS2 navigation infrastructure needed for localization, planning, and goal execution on a known map. This focused stack avoids maintaining unrelated robot models, bridge code, and simulator-specific tooling that are not required for the museum guide objective.

## Current Repository Structure

```text
dockerfiles/
  Dockerfile.tiago_museum        # ROS2 Humble image with TIAGo public simulation dependencies

start_museum_tiago.sh            # Helper script to start the Docker container with X11 support

exchange/
  museum_ws/                     # ROS2 workspace for museum-specific packages
    src/
      museum_assistant/          # Minimal Python package for semantic and ambient nodes

docs/                            # Setup notes and project documentation
```

Booster, Circus, SimBridge, Webots, and Pixi are not used in this project. The repository is now scoped to the TIAGo/Gazebo/Nav2 museum-guide track.

## Requirements On The Host

The host machine should provide:

- Ubuntu 22.04
- Git
- Docker Engine
- NVIDIA driver, if GPU acceleration is available
- NVIDIA Container Toolkit, if GPU acceleration is available
- X11 display access for Gazebo and RViz windows

ROS2, Gazebo, Nav2, SLAM Toolbox, and the TIAGo public simulation workspace are installed inside the Docker image. They do not need to be installed on the host.

## Build Docker Image

Build the Docker image from the repository root:

```bash
docker build -t museum-tiago:humble -f dockerfiles/Dockerfile.tiago_museum dockerfiles
```

The image is tagged as `museum-tiago:humble`.

## Start The Container

From the repository root:

```bash
chmod +x start_museum_tiago.sh
./start_museum_tiago.sh
```

The script starts the `museum-tiago:humble` image with host networking, X11 display access for Gazebo/RViz, optional GPU support when available, and the repository mounted at `/root/exchange`.

## Launch TIAGo In Gazebo

Inside the container:

```bash
ros2 launch tiago_gazebo tiago_gazebo.launch.py is_public_sim:=True
```

This launches the public TIAGo simulation in Gazebo. At the current stage, this is used to validate the container, ROS2 environment, Gazebo integration, and TIAGo model before adding the museum world and navigation configuration.

## Control TIAGo Manually

Open a second terminal on the host and enter the running container:

```bash
docker exec -it museum_tiago bash
```

List relevant velocity and base-control topics:

```bash
ros2 topic list | grep -E "cmd|vel|base"
```

Publish a short forward velocity command on `/mobile_base_controller/cmd_vel_unstamped`:

```bash
ros2 topic pub --once /mobile_base_controller/cmd_vel_unstamped geometry_msgs/msg/Twist \
  "{linear: {x: 0.2, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

Stop the robot:

```bash
ros2 topic pub --once /mobile_base_controller/cmd_vel_unstamped geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

Manual base movement is the next validation step before configuring Nav2 behavior in a museum map.

## Current Status

Working now:

- The Docker image builds successfully.
- The container starts from `start_museum_tiago.sh`.
- Gazebo opens.
- TIAGo is visible in the PAL office world.

Next validation:

- Verify manual base movement through the velocity command topic.

Planned features such as museum-world navigation, semantic reasoning, ambient-aware planning, LLM-based request parsing, and vision-based guide/staff recognition are not yet complete.

## Roadmap

1. Verify manual base movement.
2. Add `teleop_twist_keyboard` to the Dockerfile.
3. Inspect TIAGo sensors and ROS2 topics.
4. Create a museum Gazebo world.
5. Create a known map using SLAM.
6. Configure Nav2 for the museum map.
7. Implement the semantic graph.
8. Implement simulated ambient sensors.
9. Implement the LLM planner.
10. Implement lightweight vision for guide/staff badge recognition.
