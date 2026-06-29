# AGENTS.md

## Project identity

This repository implements **Semantic Museum Guide Robot with Ambient-Aware Reasoning**, a university HRAI project based on a TIAGo robot simulated in Gazebo.

The project goal is to build a robot museum guide that can:

* navigate in an indoor museum environment;
* use a known geometric map for robot navigation;
* maintain a semantic graph of rooms, artworks, people, roles, sensors, and dynamic states;
* reason over user requests, museum context, crowd levels, room status, and user preferences;
* explain its decisions to the user;
* later use lightweight vision to support role-aware interaction, such as detecting whether the current speaker is a guide/staff member or a visitor.

The project must stay focused on HRI + robotics + AI/GenAI reasoning. Avoid implementing isolated demos that do not affect robot behavior.

## Current validated baseline

The following baseline is working:

* Docker image `museum-tiago:humble` builds successfully.
* The container starts through `start_museum_tiago.sh`.
* Gazebo opens successfully.
* TIAGo is visible in the PAL office world.
* Manual teleoperation works.

Do not break this baseline.

## Hardware and host constraints

The target development machine is Ubuntu 22.04 with limited resources:

* about 8 GB RAM;
* 8 GB swap;
* NVIDIA GeForce MX130 with 2 GB VRAM;
* limited free disk space.

Therefore:

* do not add heavy dependencies unless explicitly requested;
* do not install ROS2, Gazebo, Nav2, or TIAGo on the host;
* keep robotics dependencies inside Docker;
* avoid local LLMs;
* avoid heavy vision stacks such as SAM, GroundingDINO, or large YOLO models unless explicitly requested;
* prefer lightweight, incremental, testable changes.

## Repository scope

This repository is focused on:

* TIAGo;
* Gazebo;
* ROS2 Humble;
* Nav2;
* known-map navigation;
* semantic graph reasoning;
* simulated ambient sensors;
* controlled LLM-based parsing/planning;
* lightweight role-aware vision in later milestones.

The project does not use:

* Booster T1;
* Circus;
* SimBridge;
* Webots;
* MuJoCo;
* Pixi;
* Booster SDK.

Do not reintroduce these stacks unless explicitly requested.

## Development philosophy

Avoid boilerplate.

Every file, node, class, launch file, or config must have a clear purpose for one of these goals:

* starting the simulation;
* moving TIAGo;
* building or using a map;
* representing semantic knowledge;
* simulating ambient museum state;
* interpreting user requests;
* choosing robot actions;
* sending navigation goals;
* explaining robot decisions;
* supporting the final demo or report.

Do not create placeholder packages, abstract frameworks, or unused layers.

Prefer small, functional modules over large generic architectures.

## ROS2 package policy

Use Python ROS2 nodes with `rclpy` unless there is a strong reason to use C++.

The main package should be:

```text
exchange/museum_ws/src/museum_assistant
```

The package should grow incrementally. The first functional nodes should be:

```text
semantic_graph_node.py
sensor_simulator_node.py
cli_node.py
```

Later nodes may include:

```text
reasoning_node.py
nav_executor_node.py
llm_planner_node.py
vision_role_node.py
```

Do not add nodes before they are needed by a milestone.

## Semantic map policy

The semantic map should represent the museum as a graph.

Use YAML for configuration and NetworkX for graph reasoning.

The semantic map should include, at minimum:

* rooms;
* artworks;
* semantic properties;
* navigation poses;
* dynamic state fields;
* role information;
* simulated sensor associations.

Example entities:

```text
Room_Impressionism
Room_AncientArt
Room_Kids
Room_TemporaryExhibition
Artwork_Monet
Role_Guide
Role_Visitor
Sensor_Crowd_Impressionism
```

Example relations:

```text
Artwork_Monet located_in Room_Impressionism
Artwork_Monet has_style Impressionism
Room_Kids suitable_for Children
TemporaryExhibition has_status Closed
CurrentSpeaker has_role Guide
```

The robot must not rely only on geometric coordinates. Semantic information must influence decisions.

## LLM policy

The LLM is not allowed to directly control the robot.

The LLM should only transform natural language into structured JSON.

Allowed LLM output example:

```json
{
  "intent": "recommend_and_navigate",
  "constraints": {
    "style": "impressionism",
    "avoid_crowd": true,
    "child_friendly": false
  }
}
```

The code must validate LLM output before using it.

Robot actions must be selected from a fixed list of skills, such as:

```text
navigate_to(location_id)
ask_clarification(question)
update_room_status(room_id, status)
recommend_alternative(reason)
explain_decision(reason)
```

Do not generate arbitrary ROS commands, shell commands, or Python code from the LLM.

## Vision policy

Vision should be introduced only after the basic reasoning and navigation pipeline works.

The first role-aware version can be mocked through a ROS2 topic, for example:

```text
/museum/current_speaker_role
```

Later, a lightweight vision node may infer whether the current speaker is a guide/staff member or a visitor using visual evidence such as:

* guide badge;
* staff lanyard;
* colored marker;
* simple sign/marker.

Do not implement face recognition or personal identity recognition.

The vision module should infer role or context, not identity.

## Navigation policy

Use Nav2 for autonomous navigation once the museum map is available.

Before Nav2 integration, manual teleop is acceptable for testing Gazebo and robot topics.

The navigation executor should receive semantic location IDs and resolve them to map poses.

Example:

```text
navigate_to("impressionism_hall")
```

should resolve to a pose stored in the semantic map or navigation config.

Do not let the LLM output raw coordinates.

## Ambient sensor policy

Ambient sensors should initially be simulated with ROS2 nodes.

Examples:

```text
/museum/room/impressionism/crowd_level
/museum/room/temporary_exhibition/status
/museum/room/kids/noise_level
```

These sensors should update the semantic graph and affect robot decisions.

For example, if a room is closed or crowded, the robot should avoid it or explain why it proposes an alternative.

## Milestones

Follow these milestones in order:

1. Stabilize Docker, Gazebo, TIAGo, and teleop.
2. Document setup in README and docs.
3. Inventory useful ROS2 topics and sensors.
4. Create minimal `museum_assistant` package.
5. Implement semantic map loading.
6. Implement simulated ambient sensors.
7. Create simple reasoning without LLM.
8. Create or adapt a museum Gazebo world.
9. Build and save a known map.
10. Integrate Nav2 goal execution.
11. Add LLM JSON parser/planner.
12. Add role-aware vision or mocked role perception.
13. Build final demo scenarios.
14. Add evaluation metrics and report material.

Do not skip directly to LLM or vision before the semantic graph and navigation base are functional.

## Coding conventions

Use clear, minimal Python.

Avoid unnecessary classes unless state or ROS2 structure requires them.

Prefer explicit functions and small nodes.

Log meaningful information with ROS2 logging.

Handle missing files, invalid YAML, invalid LLM JSON, and unknown locations gracefully.

Avoid hardcoded absolute host paths.

Keep configuration in YAML files under package `config/`.

## Docker policy

Keep Docker dependencies minimal.

Do not modify the Dockerfile for every small Python dependency.

Before adding a dependency, verify whether it is needed for the current milestone.

Do not install packages on the host when they belong inside Docker.

The main image is:

```text
museum-tiago:humble
```

The main Dockerfile is:

```text
dockerfiles/Dockerfile.tiago_museum
```

The main launcher is:

```text
start_museum_tiago.sh
```

## Git workflow

Work in small commits.

Before committing, run:

```bash
git status
git diff --stat
```

Do not commit generated build folders such as:

```text
build/
install/
log/
__pycache__/
```

Do not commit large model weights, datasets, Docker caches, or generated maps unless explicitly needed.

Commit messages should describe the functional milestone, for example:

```text
Add semantic map loader
Add ambient sensor simulator
Add TIAGo startup documentation
```

## Done criteria for new features

A feature is considered done only if:

* it runs inside the Docker/container workflow;
* it has a clear command to test it;
* it affects the robot pipeline or project demo;
* it is documented briefly;
* it does not break the existing Gazebo/TIAGo/teleop baseline.
