# User Manual — Semantic Museum Guide Robot

## Overview

This repository contains a ROS 2 Humble / Gazebo simulation of a TIAGo museum guide robot with semantic reasoning, file-based speech-to-text, visitor-session and escort supervision, Nav2 navigation, animated human Actors, and human-aware local motion.

The recommended submission demos are:

1. an eight-Actor social-navigation run with Gazebo, RViz, Nav2, the custom anisotropic `ProxemicForceCritic`, and explicit social yielding;
2. a one-Actor scene-graph reasoning demo that resolves a semantic request without starting navigation.

The project also contains separate acceptance and benchmark scripts for speech, language, reasoning, navigation, escort, and social-navigation components.

## Prerequisites

- Ubuntu host with Docker available;
- X11 desktop session for Gazebo/RViz GUI runs;
- Docker image built as `museum-tiago:humble`;
- ROS 2 Humble and TIAGo dependencies are provided inside the image;
- optional Groq API access only for the live speech-to-text acceptance script.

## Repository Paths

Host repository:

```bash
~/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
```

Repository mount inside the container:

```bash
/root/exchange
```

ROS 2 workspace inside the container:

```bash
/root/exchange/exchange/museum_ws
```

## Build the Docker Image

From the repository root:

```bash
docker build -f dockerfiles/Dockerfile.tiago_museum -t museum-tiago:humble .
```

## Start the Interactive Container

```bash
./start_museum_tiago.sh
```

The script starts an interactive container named `museum_tiago`, forwards the host display, mounts the repository at `/root/exchange`, and forwards Groq-related environment variables only when they are present in the host shell.

Inside the container, build the project packages:

```bash
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant museum_social_critic museum_video1_actors
source install/setup.bash
```

## Final Demo 1 — Eight-Actor Social Navigation

Run this directly from a host terminal in the repository root:

```bash
./scripts/stop_video1_animated_demo.sh 2>/dev/null || true
./scripts/start_video1_final_animated_demo.sh --actors 8 --runtime-audit
```

The launcher starts the complete recorded scene automatically:

- supplied museum navigation world;
- TIAGo;
- eight animated Gazebo Actors;
- `/people` bridge;
- Nav2;
- custom anisotropic `museum_social_critic::ProxemicForceCritic`;
- explicit social-yield filter;
- Gazebo GUI;
- RViz;
- compact runtime monitor;
- one automatic `NavigateToPose` goal.

The robot moves through Nav2. The Actor plugins never teleport or directly command TIAGo. Human-aware behavior is driven by the `/people` stream plus the existing local navigation stack.

The tested `walk.dae` Actor asset does not generate reliable returns at TIAGo's laser plane in this exact configuration. LiDAR remains enabled for museum geometry, while animated people are supplied to the social layer through `/people`.

Stop the demo with:

```bash
./scripts/stop_video1_animated_demo.sh
```

Gazebo and RViz intentionally remain open after the navigation result so the final state can be inspected until the stop helper is called.

## Final Demo 2 — Scene Graph and Semantic Reasoning

Start:

```bash
./scripts/start_video2_reasoning_demo.sh
```

Stop:

```bash
./scripts/stop_video2_reasoning_demo.sh
```

The demo uses one animated Actor and the existing semantic graph/reasoning pipeline. Its request is:

```text
I want to see classical art.
```

The reasoning chain uses existing graph facts, including:

```text
roman_statue : style = classical
roman_statue -> located_in -> ancient_art_hall
ancient_art_hall -> south_west_gallery
```

The monitor displays the actual request, session/reasoning state, selected semantic entities, and prepared navigation action. Navigation is intentionally not started in this demo.

## File-Based Speech-to-Text Acceptance

The project includes a live file-based speech-to-text acceptance script. Provide a real WAV file and expose `GROQ_API_KEY` in the shell environment:

```bash
PHASE8_SKIP_DOCKER_BUILD=1 \
./scripts/phase8_live_acceptance.sh /path/to/request.wav
```

The validated test format is:

```text
WAV
PCM signed 16-bit
mono
16000 Hz
```

The live acceptance performs real external transcription through the configured Groq Whisper model, then feeds the transcript into the existing language/parser/reasoning chain. The API key is never stored in the repository and should not be printed or committed.

## Manual ROS 2 Development Workflow

For manual work, start `./start_museum_tiago.sh`, then source the workspaces in every new container terminal:

```bash
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
cd /root/exchange/exchange/museum_ws
source install/setup.bash
```

### Launch TIAGo in the lightweight museum

```bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

### Launch the supplied museum scene

```bash
ros2 launch museum_assistant tiago_supplied_museum_world.launch.py
```

### Launch known-map Nav2

```bash
ros2 launch museum_assistant museum_navigation.launch.py
```

Check lifecycle state:

```bash
for node in map_server amcl planner_server controller_server bt_navigator behavior_server; do
  ros2 lifecycle get "/$node"
done
```

The active Nav2 lifecycle state is:

```text
active [3]
```

### Launch the deterministic reasoner

```bash
ros2 run museum_assistant reasoning_node
```

### Launch the visitor session

```bash
ros2 launch museum_assistant visitor_session.launch.py
```

### Launch semantic navigation

```bash
ros2 launch museum_assistant semantic_navigation.launch.py
```

### Observe main outputs

```bash
ros2 topic echo /museum/assistant_response
```

```bash
ros2 topic echo /museum/navigation_result
```

```bash
ros2 topic echo /museum/escort_state
```

## Semantic Graph Queries

Launch:

```bash
ros2 launch museum_assistant semantic_graph.launch.py
```

Example queries:

```bash
ros2 run museum_assistant museum_query --style impressionism --avoid-crowd
ros2 run museum_assistant museum_query --child-friendly
ros2 run museum_assistant museum_query --wheelchair-accessible
```

These commands exercise semantic selection without robot motion.

## Ambient Reasoning

```bash
ros2 launch museum_assistant ambient_reasoning.launch.py
```

This publishes simulated ambient state and updates the semantic graph with room crowd, noise, and availability information.

## Semantic Navigation Request

With the session, reasoner, Nav2, and semantic-navigation nodes running, an executable request can be sent as:

```bash
ros2 topic pub --once /museum/user_request std_msgs/msg/String \
  "{data: '{\"request_id\":\"museum_demo_001\",\"session_id\":\"session_1\",\"intent\":\"recommend_and_prepare_navigation\",\"constraints\":{\"style\":\"impressionism\"}}'}"
```

The reasoner resolves semantic constraints first. Raw language or LLM output does not provide arbitrary robot coordinates.

## Escort Supervision

The escort state machine supervises a visitor while Nav2 executes the semantic destination. Published states include:

```text
ESCORTING
WAITING
LOST
ARRIVED
```

The current implementation may cancel the active Nav2 goal when the visitor is too far behind and reissue the same semantic destination when the visitor catches up. This is expected behavior of the existing escort implementation.

The detailed state-machine description and thresholds are documented in `docs/social_escort.md`.

## Social Navigation

The final social-navigation system uses:

```text
/people
  -> anisotropic ProxemicForceCritic
  -> DWB trajectory scoring
  -> social-yield filter
  -> TIAGo motion command
```

The final demo keeps the escorted/interaction visitor concept separate from surrounding bystanders. In the accepted final video configuration, moving Actor state is obtained from simulation and published through `/people`; this is intentionally different from claiming generic real-world people tracking.

The social-yield monitor exposes states such as:

```text
CLEAR
SLOW
YIELDING
RESUMING
```

Detailed mathematics, parameters, and validation evidence are in `docs/human_aware_navigation.md` and `docs/video1_final_animated_demo.md`.

## Useful Debug Commands

```bash
ros2 topic list | grep -E "scan|odom|tf|map|amcl|cmd_vel|costmap|people|museum"
```

```bash
ros2 topic info /scan_raw
ros2 topic info /people
ros2 topic echo /amcl_pose --once
ros2 node list
ros2 action list | grep navigate
```

On the host, inspect active demo containers with:

```bash
docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}'
```

## Troubleshooting

### `Package museum_assistant not found`

```bash
cd /root/exchange/exchange/museum_ws
source install/setup.bash
```

Rebuild if necessary:

```bash
colcon build --symlink-install --packages-select museum_assistant museum_social_critic museum_video1_actors
```

### `ros2: command not found`

```bash
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
```

### `No such container: museum_tiago`

Start it from the repository root:

```bash
./start_museum_tiago.sh
```

### Gazebo/RViz remain open after a demo

For Video 1:

```bash
./scripts/stop_video1_animated_demo.sh
```

For Video 2:

```bash
./scripts/stop_video2_reasoning_demo.sh
```

If a development container remains active, inspect it with `docker ps` and stop the specific owned container instead of killing unrelated host processes.

## Current Limitations

- The final animated human-state stream is simulation-derived, not a generic real-world people tracker.
- The tested `walk.dae` Actor mesh is not reliably detected by TIAGo's LiDAR plane in the final simulation configuration.
- The speech interface is file based; microphone streaming and TTS are not part of the submitted runtime.
- Not every configured semantic room pose has the same amount of runtime acceptance evidence as the main demonstrated routes.
- The project is a university simulation prototype, not a certified collision-safety system.

## Recommended Evaluation Sequence

For a short demonstration or grading session:

1. run the eight-Actor social-navigation demo;
2. show the runtime monitor during CLEAR/SLOW/YIELDING/RESUMING transitions;
3. stop the demo;
4. run the scene-graph reasoning demo;
5. optionally show the independent file-based STT acceptance output;
6. inspect `benchmarks/` for the quantitative comparisons used in the report.
