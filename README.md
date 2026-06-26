# Semantic Museum Guide Robot

## Project concept

This project implements a semantic-aware museum guide robot in simulation. The robot acts as an intelligent assistant for museum visitors: it receives natural language requests, reasons over a semantic representation of the museum, uses dynamic information from simulated environmental sensors, and navigates to the most suitable location using ROS2 navigation.

The goal is to avoid a purely geometric navigation demo. The robot should not only move to predefined coordinates, but infer suitable destinations from user needs, museum knowledge, room status, crowd levels, accessibility constraints, and the role of the person interacting with it.

## Scenario

The simulated museum contains an entrance hall, multiple exhibition rooms, a main corridor, a temporary exhibition area, a kids/interactive room, an exit area, and a museum shop.

Example user requests:

* “I would like to see something impressionist, but not in a crowded area.”
* “I only have ten minutes. Show me something important near the exit.”
* “I am visiting with a child. What do you recommend?”
* “Take me to the temporary exhibition.”
* “Why did you choose this room?”

## Robot and simulation

The target robot is TIAGo simulated in Gazebo. The robot uses a known map of the museum, generated during development with SLAM and later loaded for navigation. Navigation is performed using ROS2 Nav2.

The project code will be developed inside the `exchange/` folder, which is shared with the Docker container provided by the course.

## Semantic map

The museum is represented through a semantic graph. Nodes represent rooms, artworks, visitors, museum staff, sensors, and abstract concepts such as artistic styles or accessibility. Edges represent relations such as `located_in`, `has_style`, `near`, `accessible_from`, `observed_by`, and `has_role`.

The semantic graph connects high-level concepts to navigation poses. For example, the request “show me something impressionist” can be resolved into an artwork, then into its room, and finally into a Nav2 goal pose.

## AI reasoning

A language model is used as a controlled parser and high-level planner. It converts natural language requests into structured JSON containing intent, constraints, preferences, and possible clarification needs. The actual robot actions are selected and validated by deterministic code.

## Vision use-case

The project includes a role-aware vision module. The robot uses its camera to detect whether the person in front of it is likely a museum guide or staff member, based on visible cues such as a badge, lanyard, uniform color, or marker. The robot does not identify the person; it only estimates the role.

This role affects reasoning. A museum guide can update the status of a room, while a normal visitor cannot directly modify the museum state.

## Simulated environmental sensors

The museum includes simulated sensors implemented as ROS2 nodes. These nodes publish dynamic information such as room crowd level, room noise level, corridor blockage, temporary exhibition status, or visitor flow.

The robot subscribes to these topics and updates the semantic graph at runtime. This allows the robot to adapt its recommendations and navigation behavior to a changing environment.

## Main components

* `museum_semantic_graph`: maintains the semantic graph and dynamic state.
* `museum_sensor_simulator`: publishes simulated environmental sensor data.
* `museum_vision_node`: detects people, guide/staff badges, signs, or crowd cues.
* `llm_planner_node`: parses user requests into structured plans.
* `reasoning_node`: combines LLM output, semantic graph, sensor state, and vision detections.
* `nav_executor_node`: sends navigation goals to Nav2.
* `explanation_node`: generates concise explanations for the user.

## Planned demo

The final demo will show three interactions:

1. A visitor asks for an artwork matching semantic preferences. The robot chooses a suitable room and navigates there.
2. A museum guide is visually recognized through a badge and updates the status of a room.
3. A visitor asks for the now-closed room. The robot refuses that destination, explains why, and proposes an alternative.

## Technologies

* Ubuntu 22.04
* Docker
* ROS2 Humble
* Gazebo
* TIAGo simulation
* Nav2
* RViz2
* Python ROS2 nodes
* NetworkX semantic graph
* JSON/YAML configuration
* LLM for controlled task parsing and reasoning
* YOLO / YOLO-World / Grounding DINO as possible vision models




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
