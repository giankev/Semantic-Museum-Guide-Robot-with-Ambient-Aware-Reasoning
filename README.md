# Semantic Museum Guide Robot with Ambient-Aware Reasoning

This university HRAI project develops a TIAGo museum assistant in ROS 2 Humble and Gazebo. The robot is intended to combine a known geometric map with semantic museum knowledge, ambient context, visitor interaction state, and explainable deterministic decisions.

The repository currently contains a working simulation and reasoning baseline. It does **not** yet contain an end-to-end autonomous visitor-guidance pipeline.

## Status At A Glance

### Implemented

- Docker image and launcher for the public TIAGo ROS 2 Humble simulation.
- Gazebo launch with TIAGo in a lightweight custom museum world.
- Manual keyboard teleoperation.
- ROS 2 topic and sensor inventory for the TIAGo simulation baseline.
- YAML semantic map with rooms, artworks, roles, sensors, relations, and room navigation poses.
- NetworkX semantic graph loading, validation, queries, and deterministic recommendations.
- Scripted ambient room-state updates for crowd, noise, and open/closed status.
- Structured JSON request validation and deterministic reasoning.
- Reasoning responses containing a selected room, explanation, abstract skill, and `nav_pose`.
- SLAM Toolbox configuration and a saved museum occupancy map.
- Known-map Nav2/AMCL bringup with DWB as the baseline local controller.
- Manual helpers to capture AMCL poses and send coordinate-based `NavigateToPose` goals.

The validated runtime baseline is documented in [the user manual](docs/user_manual.md). Nav2 is functional but still needs goal calibration and tuning for some map regions.

### Partially Implemented

- **Natural-language interaction:** `/museum/user_request` accepts validated JSON, but there is no natural-language parser, LLM, speech-to-text, or dialogue input.
- **Semantic-to-navigation bridge:** reasoning produces `selected_room`, `skill`, and `nav_pose`, but no interaction manager or behavior executive consumes the response and sends a Nav2 goal.
- **Ambient world state:** updates are scripted and in memory. There is no shared persistent world-model service or task-time re-reasoning policy.
- **Navigation poses:** poses exist in the semantic YAML, but they must be calibrated and verified against free space in the saved occupancy map.
- **Roles and people:** roles are represented semantically and the world contains static visual markers, but there is no person tracking, engagement perception, session identity, or role perception.

### Next Milestone

Phase 1 is to define the module interfaces and state models for:

- transient `PersonTrack` identifiers;
- visitor `Session` identifiers and lifecycle;
- validated structured requests;
- reasoning decisions;
- interaction and task state;
- abstract behavior commands and navigation results.

This phase must preserve the rule that simulation actor/model IDs stop at the perception boundary. Reasoning and interaction modules should use `PersonTrack` and `Session` IDs only.

No new runtime feature from that phase is implemented in this audit.

### Future Work

1. Add a visitor Session Manager and simulated person-ID adapter.
2. Connect deterministic reasoning to an Interaction Manager, Behavior Executive, and Nav2.
3. Add a social Escort Supervisor above Nav2 using simulated visitor ground truth.
4. Introduce a generic people publisher/tracking abstraction.
5. Add human-aware local navigation while preserving DWB as the comparison baseline.
6. Add deterministic natural-language parsing with a controlled LLM fallback.
7. Add faster-whisper speech-to-text.
8. Add grounded response generation and text-to-speech.
9. Re-reason when relevant ambient state changes during an active task.
10. Optionally add lightweight role/context perception without identifying people.
11. Evaluate baseline, semantic/ambient-aware, and social variants.

See [Architecture](docs/architecture.md) for module boundaries and [Repository Audit](docs/repository_audit.md) for the evidence behind these classifications.

## Current Runtime Shape

The implemented components form two adjacent but not yet connected paths:

```text
Scripted/manual JSON request       Scripted ambient update
              \                         /
               -> deterministic reasoning
                  -> /museum/assistant_response
                     (no runtime consumer yet)

Manual coordinate or RViz goal
              -> Nav2 + AMCL + saved map
                 -> DWB local controller
                    -> TIAGo
```

The target architecture adds perception, sessions, language, interaction management, behavior execution, and escort supervision between the human and Nav2. Social escort and social navigation are deliberately separate:

- **Social escort** decides whether the guidance task is succeeding socially.
- **Social navigation** controls how the robot moves around people.

## Repository Layout

```text
dockerfiles/
  Dockerfile.tiago_museum

start_museum_tiago.sh

exchange/museum_ws/src/museum_assistant/
  config/                 # Semantic map, Nav2, and SLAM configuration
  launch/                 # Museum, reasoning, SLAM, and Nav2 launches
  maps/                   # Saved occupancy map
  museum_assistant/       # Python nodes and deterministic logic
  worlds/                 # Lightweight Gazebo museum world
  package.xml
  setup.py

docs/
  architecture.md         # Current and target module architecture
  repository_audit.md     # Implemented/prototype/planned/obsolete audit
  user_manual.md          # Build, launch, demo, and troubleshooting commands
  raw/                    # Captured ROS 2 baseline evidence
```

Booster, Circus, SimBridge, Webots, MuJoCo, Pixi, and Booster SDK are out of scope.

## Host Requirements

- Ubuntu 22.04 or a compatible Linux host
- Git and Docker Engine
- X11 display access for Gazebo and RViz
- Optional NVIDIA driver and NVIDIA Container Toolkit

ROS 2, Gazebo, Nav2, SLAM Toolbox, TIAGo, and Python reasoning dependencies stay inside Docker.

## Build And Start

From the repository root:

```bash
docker build -f dockerfiles/Dockerfile.tiago_museum -t museum-tiago:humble .
./start_museum_tiago.sh
```

Inside the container:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant
source install/setup.bash
```

Launch TIAGo in the museum:

```bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

Launch the deterministic reasoning demo in another sourced terminal:

```bash
ros2 launch museum_assistant reasoning_demo.launch.py
ros2 topic echo /museum/assistant_response
```

Launch known-map Nav2 separately:

```bash
ros2 launch museum_assistant museum_navigation.launch.py
```

The complete workflows, terminal setup, lifecycle checks, and goal commands are in [the user manual](docs/user_manual.md).

## Safety And Architectural Constraints

- Natural-language or LLM output may only become validated structured data.
- An LLM must never emit arbitrary ROS commands, coordinates, shell commands, or code for execution.
- Robot actions must come from a fixed skill set.
- Semantic location IDs must be resolved to verified poses inside the robot-control boundary.
- Gazebo actor/model IDs must not leak into reasoning or interaction logic.
- Social escort must remain above Nav2; human-aware motion belongs in the navigation layer.
- Role perception may infer transient role/context cues, never personal identity.
