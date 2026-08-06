# Semantic Museum Guide Robot with Ambient-Aware Reasoning

This university HRAI project develops a TIAGo museum assistant in ROS 2 Humble and Gazebo. The robot is intended to combine a known geometric map with semantic museum knowledge, ambient context, visitor interaction state, and explainable deterministic decisions.

The repository contains a validated semantic-navigation chain, a minimal
simulation-ground-truth escort prototype, and an opt-in first social-costmap
experiment plus a separate runtime-validated bounded proxemic DWB critic. It
is not a real-perception system or a broad social-navigation evaluation.

## Status At A Glance

### Implemented

- Docker image and launcher for the public TIAGo ROS 2 Humble simulation.
- Gazebo launch with TIAGo in a lightweight custom museum world.
- Separate opt-in launch for the packaged supplied museum assets, with a
  runtime-validated minimal collision repair. Its occupancy-map/Nav2 gate is
  still incomplete, so it is not the default environment.
- Manual keyboard teleoperation.
- ROS 2 topic and sensor inventory for the TIAGo simulation baseline.
- YAML semantic map with rooms, artworks, roles, sensors, relations, and room navigation poses.
- NetworkX semantic graph loading, validation, queries, and deterministic recommendations.
- Scripted ambient room-state updates for crowd, noise, and open/closed status.
- Structured JSON request validation and deterministic reasoning.
- Reasoning responses containing a selected room, explanation, abstract skill, and `nav_pose`.
- Minimal ROS-independent Phase 1 data models for person tracks, session state,
  structured requests, reasoning decisions, and the reasoner's current skills.
- Minimal Phase 2 simulation identity and in-memory visitor session published
  on `/museum/session_state`.
- Focused Phase 3 semantic-navigation path that sends explicitly prepared
  successful decisions to Nav2 and publishes correlated navigation results.
- Minimal Phase 4 visitor observation and escort supervision with
  `ESCORTING`, `WAITING`, `LOST`, and `ARRIVED` states.
- Intentional Nav2 cancel/resume when the static simulated visitor lags and
  joint robot-plus-visitor arrival as escort success.
- Opt-in bounded scripted visitor motion for a repeatable Phase 4 lag-recovery
  demo; manual marker control remains available.
- Opt-in Phase 5 `/people` stream using standard
  `social_nav_msgs/msg/Pedestrians` for the three Gazebo human markers, with
  finite-difference planar velocities.
- Opt-in Phase 6 compatibility bridge from `/people` to the third-party-only
  `people_msgs/msg/People` boundary.
- Separate Nav2 + DWB + UPO social local-costmap launch; the original Nav2 +
  DWB launch and configuration remain unchanged.
- SLAM Toolbox configuration and a saved museum occupancy map.
- Known-map Nav2/AMCL bringup with DWB as the baseline local controller.
- Manual helpers to capture AMCL poses and send coordinate-based `NavigateToPose` goals.

The validated runtime baseline is documented in [the user manual](docs/user_manual.md).
The Phase 4 automatic and manual procedures are in
[Social Escort](docs/social_escort.md).
The simulation people boundary is in
[Simulated People](docs/simulated_people.md).
The Phase 6 experiments and accepted bounded custom-critic result are in
[Human-Aware Navigation](docs/human_aware_navigation.md).
The bounded Phase 8 file interface and its cloud-audio privacy boundary are in
[Speech Interface](docs/speech_interface.md).
The supplied-world asset, Gazebo, collision, and rejected-map evidence is in
[Supplied Museum Integration](docs/supplied_museum_integration.md).

### Partially Implemented

- **Supplied museum environment:** the original DAE and textures are packaged
  without host-specific paths, TIAGo and its sensors run in the dedicated
  world, and physical north/east routes were exercised. Repeated SLAM attempts
  did not yield a map with sufficient aligned clearance, so supplied-world
  AMCL, Nav2, semantic, escort, people, social, and Phase 7 regressions remain
  unaccepted. The previous world remains the default.
- **Natural-language interaction:** Phase 7 is a runtime-validated bounded
  text-language prototype with deterministic Italian/English parsing, strict
  Groq Structured Outputs, and unchanged local validation. Phase 8 now adds a
  bounded file-based Groq transcription input with offline tests passing; its
  operator-supplied live audio acceptance and dialogue remain pending.
- **Semantic-to-navigation bridge:** `semantic_navigation_node` consumes only
  successful `recommend_and_prepare_navigation` decisions and sends their
  deterministic `nav_pose` to Nav2. The complete chain has passed runtime
  acceptance for `impressionism_hall`; other semantic poses still require
  individual calibration.
- **Ambient world state:** updates are scripted and in memory. There is no shared persistent world-model service or task-time re-reasoning policy.
- **Navigation poses:** poses exist in the semantic YAML, but they must be calibrated and verified against free space in the saved occupancy map.
- **Roles and people:** roles are represented semantically. The static
  `visitor_marker` is detected through Gazebo ground truth for the Phase 2
  demo. Phase 5 also exposes the visitor, guide, and staff markers on `/people`,
  but there is no real person tracking, engagement perception, or role
  perception.
- **Sessions and downstream modules:** one minimal in-memory session and one
  escort task are supported for the static simulated visitor. There are no
  preferences, history, persistence, Interaction Manager, Behavior Executive,
  or general task framework.

### Current Milestone

Phase 6 is a runtime-validated bounded prototype through the separate
`museum_social_critic::ProxemicForceCritic` at scale 32. The accepted run
increased controlled minimum guide clearance from `0.603 m` to `0.665 m` while
preserving navigation and escort completion. Phase 7 is now a
runtime-validated bounded text-language prototype. Phase 8 file-based
speech-to-text is implemented and passes the selected automated suite; it is
not marked runtime-validated until the live audio acceptance succeeds.
The supplied museum is separately integrated through the Gazebo/sensor gate,
but remains PARTIAL at the occupancy-map gate and has not replaced the
validated lightweight-world baseline.

### Future Work

1. Calibrate the remaining semantic navigation poses used by final demos.
2. Introduce Interaction Manager and Behavior Executive only when their
   runtime policies are required.
3. Replace simulation ground truth with real or generic people tracking only
   after the standard `/people` boundary is validated.
4. Complete the Phase 8 operator-supplied live audio acceptance.
5. Add grounded response generation and text-to-speech.
6. Re-reason when relevant ambient state changes during an active task.
7. Optionally add lightweight role/context perception without identifying people.
8. Evaluate baseline, semantic/ambient-aware, and social variants.

See [Architecture](docs/architecture.md) for module boundaries and [Repository Audit](docs/repository_audit.md) for the evidence behind these classifications.

## Current Runtime Shape

The simulated session is correlated through reasoning and the focused semantic
navigation adapter:

```text
visitor_marker -> /gazebo/model_states -> visitor_session_node
                                      -> /museum/session_state
                                      -> /museum/visitor_observation
                                      -> scripted structured request
                                      -> deterministic reasoning
                                      -> /museum/assistant_response
                                      -> semantic_navigation_node
                                           |               |
                                           v               v
                              /museum/escort_state    NavigateToPose
                                                           |
                                                           v
                                               Nav2 + AMCL + saved map
                                                           |
                                                           v
                                                    DWB -> TIAGo
                                                           |
                                                           v
                                          /museum/navigation_result

Optional simulation-only demo path:
/museum/escort_state + /gazebo/model_states
                 -> scripted_visitor_node
                 -> /gazebo/set_entity_state -> visitor_marker

Optional Phase 6 social-navigation sidecar:
/gazebo/model_states -> simulated_people_node -> /people
                 -> social_people_bridge_node -> /people_nav2
                 -> UPO social local-costmap layer -> DWB
```

The target architecture adds real perception, language, interaction
management, and behavior execution. Social escort and social navigation remain
deliberately separate:

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
    contracts.py          # Minimal ROS-independent Phase 1 data models
    escort.py             # Minimal Phase 4 escort state machine
    scripted_visitor.py   # Bounded lag-recovery marker motion
    scripted_visitor_node.py
    simulated_people.py   # Stable IDs and finite-difference velocities
    simulated_people_node.py
    social_people_bridge.py
    social_people_bridge_node.py
    semantic_navigation.py
    semantic_navigation_node.py
    visitor_session.py    # Minimal in-memory Phase 2 session logic
    visitor_session_node.py
  test/                   # Contract, session, escort, and reasoning tests
  worlds/                 # Lightweight baseline and packaged supplied museum
    supplied_museum/      # Original visual assets plus bounded collision DAE
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

Launch the separate supplied-museum Gazebo variant (currently asset and
physical-motion validation only):

```bash
ros2 launch museum_assistant tiago_supplied_museum_world.launch.py gzclient:=false
```

Do not pair this variant with the legacy saved map. Its mapping/Nav2 gate is
documented as PARTIAL in
[Supplied Museum Integration](docs/supplied_museum_integration.md).

Launch the deterministic reasoning demo in another sourced terminal:

```bash
ros2 launch museum_assistant reasoning_demo.launch.py
ros2 topic echo /museum/assistant_response
```

## Phase 2 Visitor Session Demo

Build the package once, then use separate sourced container terminals.

Terminal 1 — launch TIAGo and the museum world:

```bash
cd /root/exchange/exchange/museum_ws
source install/setup.bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

Terminal 2 — launch the one-node session adapter:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 launch museum_assistant visitor_session.launch.py
```

Terminal 3 — observe the periodically published active session:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/session_state
```

The public JSON contains `session_1`, `visitor_1`, and `active`; it does not
contain the Gazebo model name.

Terminal 4 — start the deterministic reasoner:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 run museum_assistant reasoning_node
```

Terminal 5 — observe assistant responses:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/assistant_response
```

Terminal 6 — send a correlated structured request:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic pub --once /museum/user_request std_msgs/msg/String \
  "{data: '{\"request_id\":\"session_demo_001\",\"session_id\":\"session_1\",\"intent\":\"recommend\",\"constraints\":{\"style\":\"impressionism\",\"avoid_crowd\":true}}'}"
```

The response contains the same `"session_id": "session_1"`. Alternatively,
`reasoning_demo.launch.py` starts the existing request simulator, which now
uses the active session ID received from `/museum/session_state`.

## Phase 3 Semantic Navigation Demo

Do not use `reasoning_demo.launch.py` for this workflow because it starts the
periodic request simulator. Run one explicit navigation request instead.

Build the package, then use separate sourced container terminals.

Terminal 1 — launch TIAGo in the museum:

```bash
cd /root/exchange/exchange/museum_ws
source install/setup.bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

Terminal 2 — launch known-map Nav2:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 launch museum_assistant museum_navigation.launch.py
```

Terminal 3 — verify Nav2 lifecycle nodes:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
for node in map_server amcl planner_server controller_server bt_navigator behavior_server; do
  ros2 lifecycle get "/$node"
done
```

All listed nodes must report `active [3]`. Set or confirm TIAGo's initial pose
in RViz before sending the navigation request. For the documented entrance
estimate:

```bash
ros2 topic pub --once /initialpose \
  geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: 0.0, y: 0.0, z: 0.0}, orientation: {z: 0.0, w: 1.0}}, covariance: [0.25, 0, 0, 0, 0, 0, 0, 0.25, 0, 0, 0, 0, 0, 0, 0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.068]}}"
```

Terminal 4 — launch only the reasoner:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 run museum_assistant reasoning_node
```

Terminal 5 — launch the Phase 2 visitor session:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 launch museum_assistant visitor_session.launch.py
```

Terminal 6 — launch only the semantic navigation adapter:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 launch museum_assistant semantic_navigation.launch.py
```

Terminal 7 — observe reasoning decisions:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/assistant_response
```

Terminal 8 — observe navigation acceptance and completion:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/navigation_result
```

Terminal 9 — send one correlated request for the Impressionism Hall:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic pub --once /museum/user_request std_msgs/msg/String \
  "{data: '{\"request_id\":\"nav_demo_001\",\"session_id\":\"session_1\",\"intent\":\"recommend_and_prepare_navigation\",\"constraints\":{\"style\":\"impressionism\"}}'}"
```

The assistant response should select `impressionism_hall`. The navigation
result first reports `accepted`, followed by `succeeded`, `aborted`, or
`canceled`.

Plain `recommend` requests never move the robot. Before the final demo, verify
the selected room pose against free space in the saved occupancy map. Use:

```bash
ros2 run museum_assistant capture_nav_pose --name impressionism_hall
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
