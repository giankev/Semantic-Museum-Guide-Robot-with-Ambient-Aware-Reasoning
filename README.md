# TIAGo + Booster T1 Simulation Stack

Integrated simulation environment for heterogeneous robots: **TIAGo** (Gazebo/ROS2) and **Booster T1** (Webots), orchestrated by **Circus** (MuJoCo) via **SimBridge** (ROS2 bridge).

## Clone the Repository

This repository uses Git submodules for `circus` and `simbridge`. Clone with:

```bash
https://github.com/Lab-RoCoCo-Sapienza/hrai-25-26-course-project-HRAI-Container
cd hrai_container
```

If you've already cloned without submodules, initialize them:

```bash
git submodule update --init --recursive
```

## Requirements

### For Docker (TIAGo/Booster Webots)
- Docker with NVIDIA GPU support (`nvidia-container-toolkit`)
- X11 display

### For Circus + SimBridge
- **pixi** — [install from pixi.sh](https://pixi.sh)

## Pixi Installation

Pixi is a cross-platform package manager (conda-based). Install the version pixi 0.59.0 from 

```bash
https://pixi.prefix.dev/latest/installation/#download-from-github-releases
```

## Installation instructions
**Build the Docker image:**
```bash
cd dockerfiles
docker build -t spqr:booster .
```

**Run TIAGo:**
```bash
bash start_tiago.sh
```

Inside the container, launch Gazebo:
```bash
ros2 launch tiago_gazebo tiago_gazebo.launch.py is_public_sim:=True
```
Check if Tiago spawn in gazebo to see if it works.


## Circus + SimBridge (Robot Booster T1 Integration)

Circus is the main simulator that manages Docker containers and physics (MuJoCo). SimBridge bridges ROS2 to Circus for sensor/actuator communication.

### Install and run Circus

```bash
cd circus
pixi install
```

The simulator will start and wait for robot containers to connect via Docker API

### Install SimBridge

SimBridge runs automatically inside robot containers created by Circus. To install standalone dependencies:

```bash
cd simbridge
pixi install
```

when all the repos are built you can run. Modify first the yaml file in circus/resources/config/path_constants.yaml with the absolute path of circus, simbridge and booster_sdk
that you can find in the repo. circus and simbdrige are in the root directory booster_sdk is into the dockerfiles directory

```bash
pixi run circus resources/scene/1vs1.yaml
```
It will spawn one container for each robot, inside each container you can see all the topics related to that robot.

### Control the robot inside the container

```bash
loco
```

#### Commands

| Key | Action |
|-----|--------|
| `mw` | Mode: Walking (stand up) |
| `w` | Walk forward |

**Startup sequence:** `mw` → wait → `w` to walk.
