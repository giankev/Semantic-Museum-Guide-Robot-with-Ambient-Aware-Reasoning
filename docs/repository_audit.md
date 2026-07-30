# Repository Audit

## Audit Scope

The Phase 0 audit was performed on branch `setup-tiago-museum` at commit
`7858233`. Phase 1 extends that audited baseline with ROS-independent contracts
and tests. The audit reviewed:

- repository history and working-tree state;
- `README.md`, `AGENTS.md`, and all current Markdown documentation;
- Python nodes and deterministic logic;
- every package launch file;
- semantic, SLAM, and Nav2 configuration;
- the saved map and Gazebo world;
- `setup.py`, `setup.cfg`, and `package.xml`;
- Docker and container launch files;
- captured ROS 2 evidence under `docs/raw/`.

The classifications below use source presence plus the validated milestones already recorded in the repository. This documentation audit did not perform a fresh Gazebo/Nav2 runtime acceptance test.

## Classification

### Implemented

| Capability | Evidence | Boundary |
| --- | --- | --- |
| TIAGo Docker/Gazebo baseline | `Dockerfile.tiago_museum`, `start_museum_tiago.sh`, validated project baseline | ROS 2/Gazebo dependencies remain in Docker. |
| Manual TIAGo movement | teleop dependency, documented command and validated baseline | Direct velocity/teleop only. |
| Custom museum scene | `worlds/museum.world`, `museum_world.launch.py` | Lightweight static geometry and visual markers. |
| TIAGo in museum world | `tiago_museum_world.launch.py`, validated milestone documentation | World launch does not itself start Nav2. |
| Semantic museum graph | `semantic_map.yaml`, `semantic_graph.py`, `semantic_graph_node.py` | YAML validation, NetworkX graph, room/artwork queries. |
| Ambient updates | `ambient_sensor_simulator_node.py`, graph update handlers | Scripted JSON and process-local memory. |
| Deterministic reasoning | `reasoning.py`, `reasoning_node.py` | Fixed intents/constraints; no natural-language parsing. |
| Structured request/response topics | `/museum/user_request`, `/museum/assistant_response` | JSON over `std_msgs/String`; simulator/manual producer. |
| Phase 1 contracts | `contracts.py`, contract/reasoning tests | Typed IDs, session lifecycle, requests, decisions, safe commands, escort states, and navigation results; no runtime managers. |
| SLAM workflow and saved map | SLAM launch/config plus `museum_map.yaml/.pgm` | Map is present; no automated quality test. |
| Known-map Nav2 baseline | `museum_navigation.launch.py`, `nav2_museum.yaml`, validated navigation notes | AMCL/Nav2/DWB; some goals/regions remain unstable. |
| Navigation test helpers | `capture_nav_pose`, `send_nav_goal` entry points | Developer tools; coordinate goal input only. |

### Prototype Or Partially Implemented

| Capability | What exists | Missing for completion |
| --- | --- | --- |
| Semantic navigation intent | Reasoner emits `selected_room`, `navigate_to`, and `nav_pose`. | No consumer, pose verification, task executive, or automatic Nav2 action. |
| Visitor request interface | Strict `StructuredRequest`, optional session correlation, and scripted JSON requests. | No text parser, dialogue, Session Manager, STT, or LLM fallback. |
| Dynamic world model | Room ambient fields update in memory. | No shared authority, persistence, timestamps, provenance, visitor/session/task facts, or task-time re-reasoning. |
| Navigation poses | Every room has a `nav_pose`; AMCL capture helper exists. | Poses are not all documented as calibrated/free-space tested. |
| Museum topology | `connected_to` relations are stored. | No route-level semantic traversal uses them; edges are directed unless reverse relations are added. |
| Roles | Visitor/guide/staff concepts and permissions are in YAML. | No current-speaker role, authorization enforcement, role perception, or session binding. |
| Human representation | Static visitor/guide/staff visual models exist in Gazebo. | They are not Gazebo actors, tracked people, engagement observations, or escort targets. |
| Navigation reliability | Nav2 activates and accepts goals. | Tuning, calibrated semantic goals, repeatability metrics, and failure handling remain incomplete. |

### Documented Or Planned Only

There is no runtime implementation for:

- person or engagement perception;
- producer of `PersonTrack` observations;
- visitor Session Manager;
- speech-to-text;
- natural-language parsing or LLM fallback;
- Interaction Manager;
- Behavior Executive;
- Social Escort Supervisor;
- people publisher/tracker abstraction;
- human-aware/social local navigation;
- grounded answer generation or TTS;
- task-time ambient adaptation;
- role-aware vision;
- comparative experimental evaluation.

### Obsolete Or Misleading Material Found

The audit found and corrected these documentation problems:

- The old README described only the early Docker/PAL-world baseline and listed already-completed semantic, world, mapping, and Nav2 work as future.
- `docs/setup_tiago_museum.md` referenced nonexistent `museum_assistant.launch.py`, `sensor_simulator_node`, and `cli_node` executables and the obsolete `/museum/ambient_status` topic.
- Early milestone pages used phrases such as “Nav2 is not integrated yet” without making clear that the statement described that historical milestone, not the current repository.
- The topic inventory treated Nav2 and ambient topics as future even though it is a snapshot captured before those milestones.
- The former roadmap jumped from Nav2 directly to LLM and vision, omitting sessions, interaction management, behavior execution, escort supervision, identity abstraction, and evaluation.
- Documentation sometimes described semantic `nav_pose` values as placeholders without separating “present in YAML” from “calibrated and proven safe for Nav2.”

## Source, Launch, And Metadata Consistency

### Console Entry Points

All executables used by current package launch files are registered in `setup.py`:

- `semantic_graph_node`
- `ambient_sensor_simulator`
- `reasoning_node`
- `user_request_simulator`

The developer helpers `museum_query`, `capture_nav_pose`, and `send_nav_goal` are also registered.

### Launch Files

| Launch file | Actual scope | Does not do |
| --- | --- | --- |
| `semantic_graph.launch.py` | Starts the graph demo node. | No ambient simulator or reasoning request interface. |
| `ambient_reasoning.launch.py` | Starts graph demo plus scripted ambient updates. | No request reasoning or Nav2. |
| `reasoning_demo.launch.py` | Starts deterministic reasoner, ambient simulator, and request simulator. | No interaction manager or navigation execution. |
| `museum_world.launch.py` | Opens the museum world without TIAGo. | No robot, SLAM, or Nav2. |
| `tiago_museum_world.launch.py` | Includes the TIAGo Gazebo launch with the museum world. | No SLAM or Nav2 in that launch. |
| `museum_slam.launch.py` | Starts async SLAM Toolbox with `/scan_raw` remapping. | No robot/world launch and no map saving automation. |
| `museum_navigation.launch.py` | Includes Nav2 bringup with saved map and museum parameters. | No robot/world launch and no semantic goal consumer. |

### Configuration And Assets

- `setup.py` installs all current YAML, launch, map, and world assets.
- The saved PGM is a 253 by 183 occupancy image referenced by `museum_map.yaml`.
- `nav2_museum.yaml` uses AMCL, NavFn, DWB, standard recovery behaviors, and the saved map launch.
- `semantic_map.yaml` contains seven rooms, five artworks, six simulated sensors, three roles, and semantic relations.
- Semantic room poses are copied directly into reasoning responses; their calibration status is not encoded.

### Package Metadata

The package manifest already declared the Python, message, and Nav2 action dependencies used by source code. This audit added explicit runtime dependencies for the installed launch files and their included systems: `launch`, `launch_ros`, `gazebo_ros`, `nav2_bringup`, `slam_toolbox`, and `tiago_gazebo`.

`setup.py` and `package.xml` now use a description that reflects the package's broader current scope instead of describing only the original semantic-map milestone.

## Current Gaps By Target Layer

| Target layer | Gap |
| --- | --- |
| Perception | No tracked-person observation or engagement signal. |
| Session | Contracts and lifecycle rules exist, but there is no manager, runtime identity mapping, or preference state. |
| Language | Only already-structured JSON; no natural language or speech. |
| World model | No shared dynamic authority and no person/session/task state. |
| Reasoning | No session-aware constraints, active-task re-reasoning, or downstream orchestration. |
| Interaction | Command contract exists; runtime manager and dialogue policy are absent. |
| Behavior | Safe command contract exists; executive and navigation adapter are absent. |
| Escort | State values exist; the social task-supervision runtime is absent. |
| Navigation | Baseline exists, but no semantic goal resolver, calibrated goal set, or human-aware local planner. |
| Evaluation | No repeatable scenarios or metrics comparing variants. |

## Coherent Milestone History

The repository history can be retained without using milestone numbers that conflict with the new architecture:

1. **Focused platform baseline:** removed unrelated stacks and established Docker, ROS 2 Humble, TIAGo, Gazebo, and teleop.
2. **Robot interface inventory:** captured relevant topics, sensors, transforms, nodes, and actions.
3. **Semantic world-model baseline:** added YAML museum knowledge, validation, NetworkX representation, and queries.
4. **Ambient reasoning baseline:** added scripted dynamic room state and deterministic recommendation updates.
5. **Structured decision baseline:** added validated JSON requests and explainable deterministic reasoning outputs.
6. **Museum simulation baseline:** added the custom world and TIAGo launch integration.
7. **Geometric navigation baseline:** added SLAM configuration, saved map, AMCL/Nav2/DWB bringup, and manual goal tools.
8. **Architecture audit and documentation cleanup:** reconciled status, module boundaries, gaps, and future phases.
9. **Contract and state-model baseline:** added typed identity/session contracts, strict request/decision serialization, safe abstract commands, and ROS-independent tests.

This history records what was achieved while leaving runtime sessions,
interaction, behavior execution, escort, language, speech, social navigation,
and perception clearly unimplemented.

## Revised Roadmap

| Phase | Deliverable | Completion test |
| --- | --- | --- |
| 0 | **Complete:** repository and documentation cleanup | Source-backed status and coherent architecture/roadmap. |
| 1 | **Complete:** module interfaces and state models | Contract validation tests cover IDs, lifecycle/state enums, allowed transitions, and invalid input. |
| 2 | **Next:** Visitor Session Manager and simulated person IDs | Gazebo identity is converted to `PersonTrack`, then to `Session`, without leaking actor IDs downstream. |
| 3 | Reasoner -> Interaction Manager -> Behavior Executive -> Nav2 | A validated structured request produces one verified semantic goal and a reported navigation result. |
| 4 | Basic escort state machine with simulated ground truth | Following, stopped, lagging, lost, recovered, and arrived transitions are reproducible. |
| 5 | Generic people publisher/tracking abstraction | Escort/session code runs unchanged against the generic interface. |
| 6 | Human-aware/social Nav2 controller | Human-aware variant runs beside an unchanged DWB baseline and can be compared. |
| 7 | Deterministic language parser plus LLM fallback | Text becomes schema-valid JSON; invalid/unsafe model output is rejected. |
| 8 | faster-whisper STT | Recorded speech produces text within measured latency/resource limits. |
| 9 | Grounded answer generation and TTS | Spoken answers cite only current request/world/task facts. |
| 10 | Active-task ambient adaptation | A relevant closure/crowd update triggers controlled re-reasoning and behavior change. |
| 11 | Optional lightweight perception | Role/context cues are inferred without personal identity recognition. |
| 12 | Experimental evaluation | Repeatable metrics compare baseline and semantic/social variants. |

## Recommended Next Implementation Task

Phase 2 should implement only the Visitor Session Manager and a lightweight
simulation identity adapter against the Phase 1 contracts. It should:

- translate Gazebo identity to `PersonTrackId` at the adapter boundary;
- create and transition `SessionState` records;
- keep Gazebo identifiers out of all downstream state;
- test creation, track/session association, valid lifecycle transitions,
  closure, and invalid reuse.

It must not add interaction, behavior execution, escort, semantic navigation,
language, speech, or vision features.
