# Repository Audit

## Audit Scope

The Phase 0 audit was performed on branch `setup-tiago-museum` at commit
`7858233`. Later phases extend that audited baseline with minimal contracts, a
simulated visitor session, an accepted semantic-navigation chain, and a minimal
simulation-ground-truth escort prototype. The
audit reviewed:

- repository history and working-tree state;
- `README.md`, `AGENTS.md`, and all current Markdown documentation;
- Python nodes and deterministic logic;
- every package launch file;
- semantic, SLAM, and Nav2 configuration;
- the saved map and Gazebo world;
- `setup.py`, `setup.cfg`, and `package.xml`;
- Docker and container launch files;
- captured ROS 2 evidence under `docs/raw/`.

The classifications below use source presence plus validated milestones. The
Phase 4 updates additionally cover the current Gazebo model-state interfaces,
manual visitor repositioning, escort pause/resume, terminal loss, joint
arrival, and a runtime-accepted opt-in deterministic lag-recovery marker
script.
Phase 5 adds a runtime-accepted opt-in standard simulation people stream
without connecting it to escort or navigation.
Phase 6 first added an opt-in bridge and UPO local social-costmap integration;
that variant's wiring passed but its behavioral comparison failed. Phase 6B
then added a separate custom proxemic DWB critic which passed the controlled
clearance, stability, and escort acceptance checks while retaining DWB.
Phase 7 adds deterministic text parsing plus a strict, one-at-a-time Groq
fallback boundary. Offline and live functional acceptance pass as a bounded
runtime-validated text-language prototype; adversarial prompt-injection
evaluation remains deferred.

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
| Phase 1 data models | `contracts.py`, contract/reasoning tests | Plain-string person/session IDs, minimal person/session state, validated requests, reasoning decisions, and current reasoner skills; no runtime managers. |
| Phase 2 visitor session | `visitor_session_node.py`, `/museum/session_state` | One static Gazebo-ground-truth visitor mapped to one in-memory active session. |
| SLAM workflow and saved map | SLAM launch/config plus `museum_map.yaml/.pgm` | Map is present; no automated quality test. |
| Known-map Nav2 baseline | `museum_navigation.launch.py`, `nav2_museum.yaml`, validated navigation notes | AMCL/Nav2/DWB; some goals/regions remain unstable. |
| Navigation test helpers | `capture_nav_pose`, `send_nav_goal` entry points | Developer tools; coordinate goal input only. |

### Prototype Or Partially Implemented

| Capability | What exists | Missing for completion |
| --- | --- | --- |
| Semantic navigation execution | `semantic_navigation_node` filters executable decisions, sends `NavigateToPose`, and publishes `/museum/navigation_result`. | The complete chain is runtime-accepted for `impressionism_hall`; other poses and repeatability evidence remain. |
| Minimal social escort | `escort.py`, `/museum/visitor_observation`, and `/museum/escort_state` support one task with intentional Nav2 pause/resume; an opt-in script makes normal lag/recovery reproducible. | Gazebo ground truth and a service-moved static marker only; no real tracking, generic people interface, obstacle-aware visitor motion, or recovery from `LOST`. |
| Simulated people stream | `simulated_people_node` maps the current visitor, guide, and staff markers to standard `social_nav_msgs/msg/Pedestrians` on `/people`; static, moving, and stopped samples are runtime-validated. | Gazebo ground truth and finite-difference velocity only; no perception, tracking, or prediction. The social consumer is opt-in. |
| Human-aware Nav2 variants | The earlier bridge/UPO-layer variant remains intact as a behavior-failed experiment. The separate `museum_social_critic` package, `nav2_museum_social_force.yaml`, and `museum_navigation_social_force.launch.py` add an accepted custom trajectory critic while retaining DWB and the baseline local costmap. | Phase 6B is accepted only for the controlled scenario: 0.665 m minimum clearance versus 0.603 m baseline at scale 32. It is not a general social-navigation evaluation, perception system, Social MPC, or learned predictor. |
| Visitor request interface | `/museum/user_text`, deterministic Italian/English parsing, optional Groq strict Structured Outputs fallback, strict local validation, existing `StructuredRequest`, and active-session correlation. | Runtime-validated only as a bounded text-language prototype; adversarial prompt-injection evaluation, dialogue, general session policy, and STT remain pending. |
| Dynamic world model | Room ambient fields update in memory. | No shared authority, persistence, timestamps, provenance, visitor/session/task facts, or task-time re-reasoning. |
| Navigation poses | Every room has a `nav_pose`; AMCL capture helper exists. | Poses are not all documented as calibrated/free-space tested. |
| Museum topology | `connected_to` relations are stored. | No route-level semantic traversal uses them; edges are directed unless reverse relations are added. |
| Roles | Visitor/guide/staff concepts and permissions are in YAML. | No current-speaker role, authorization enforcement, role perception, or session binding. |
| Human representation | The static visitor supplies simulation-ground-truth presence and robot distance; an opt-in node can move the marker for one script. | It is not an autonomous Gazebo actor, tracked person, engagement observation, or real perception output. |
| Navigation reliability | Nav2 activates and the accepted Impressionism goal succeeds. | Remaining semantic goals, repeatability metrics, and broader failure evidence remain incomplete. |

### Documented Or Planned Only

There is no runtime implementation for:

- person or engagement perception;
- real producer of tracked-person observations;
- general multi-visitor Session Manager;
- speech-to-text;
- Interaction Manager;
- Behavior Executive;
- real or generic people tracking source;
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
- `language_node`
- `visitor_session_node`
- `semantic_navigation_node`
- `scripted_visitor_node`
- `simulated_people_node`
- `social_people_bridge_node`
- `user_request_simulator`

The developer helpers `museum_query`, `capture_nav_pose`, and `send_nav_goal` are also registered.

### Launch Files

| Launch file | Actual scope | Does not do |
| --- | --- | --- |
| `semantic_graph.launch.py` | Starts the graph demo node. | No ambient simulator or reasoning request interface. |
| `ambient_reasoning.launch.py` | Starts graph demo plus scripted ambient updates. | No request reasoning or Nav2. |
| `reasoning_demo.launch.py` | Starts deterministic reasoner, ambient simulator, and request simulator. | No interaction manager or navigation execution. |
| `language.launch.py` | Starts only the deterministic-first text parser and optional Groq fallback node. | No reasoner, Nav2, visitor session, escort, people publisher, STT, or TTS. |
| `visitor_session.launch.py` | Starts the simulated visitor-session and public distance-observation adapter. | No reasoning, navigation, generic people tracking, or real perception. |
| `semantic_navigation.launch.py` | Starts the filtered reasoning-to-Nav2 adapter with minimal escort state logic. | No Nav2 bringup, reasoner, task manager, Behavior Executive, or social navigation. |
| `scripted_visitor.launch.py` | Opt-in bounded movement of `visitor_marker` for one deterministic lag-recovery demo. | No escort decisions, tracking, perception, path planning, obstacle avoidance, or social navigation. |
| `people.launch.py` | Opt-in standard `/people` publisher for three existing Gazebo markers. | No tracking, perception, costmap integration, controller, or social navigation. |
| `social_people_bridge.launch.py` | Opt-in minimal `/people` to `/people_nav2` compatibility bridge. | No tracking, prediction, identity, session, escort, or navigation logic. |
| `museum_world.launch.py` | Opens the museum world without TIAGo. | No robot, SLAM, or Nav2. |
| `tiago_museum_world.launch.py` | Includes the TIAGo Gazebo launch with the museum world. | No SLAM or Nav2 in that launch. |
| `museum_slam.launch.py` | Starts async SLAM Toolbox with `/scan_raw` remapping. | No robot/world launch and no map saving automation. |
| `museum_navigation.launch.py` | Includes Nav2 bringup with saved map and museum parameters. | No robot/world launch or semantic adapter in the same launch. |
| `museum_navigation_social.launch.py` | Includes the same Nav2/DWB stack with the opt-in UPO layer in the local costmap. | No people publisher, bridge, reasoner, semantic adapter, escort script, or Social MPC. |
| `museum_navigation_social_force.launch.py` | Includes baseline Nav2/DWB with the accepted opt-in `ProxemicForceCritic` and baseline obstacle/inflation local costmap. | No people publisher, reasoner, semantic adapter, escort script, full Social Force Model, or Social MPC. |

### Configuration And Assets

- `setup.py` installs all current YAML, launch, map, and world assets.
- The saved PGM is a 300 by 220 occupancy image referenced by `museum_map.yaml`.
- `nav2_museum.yaml` uses AMCL, NavFn, DWB, standard recovery behaviors, and the saved map launch.
- `nav2_museum_social.yaml` preserves the baseline global costmap and DWB
  parameters and adds only the UPO layer to the local costmap.
- `nav2_museum_social_force.yaml` starts from the baseline, retains its local
  costmap, and adds only the custom proxemic trajectory critic to DWB.
- `semantic_map.yaml` contains seven rooms, five artworks, six simulated sensors, three roles, and semantic relations.
- Semantic room poses are copied directly into reasoning responses; their calibration status is not encoded.

### Package Metadata

The Python package manifest declares the message and Nav2 action dependencies
used by its source. The Docker image pins the official OpenAI Python SDK used
for the Groq-compatible Phase 7 request. Phase 5 adds `social_nav_msgs` from
apt. The earlier Phase 6
experiment builds pinned `people_msgs` and `nav2_social_costmap_plugin` in a
separate overlay because `ros-humble-people-msgs` was unavailable. The new
`ament_cmake` package builds one plugin library from existing Humble DWB,
pluginlib, TF, costmap, and message dependencies; it does not patch or overlay
Nav2.

`setup.py` and `package.xml` now use a description that reflects the package's broader current scope instead of describing only the original semantic-map milestone.

## Current Gaps By Target Layer

| Target layer | Gap |
| --- | --- |
| Perception | A Gazebo-ground-truth `/people` stream exists, but there is no real tracked-person or engagement signal. |
| Session | One static visitor-to-session mapping exists; there is no general lifecycle, disappearance, persistence, or multi-visitor policy. |
| Language | The bounded deterministic-first text and strict cloud-fallback prototype passed offline and live functional acceptance; adversarial evaluation and all speech input/output remain pending. |
| World model | No shared dynamic authority and no person/session/task state. |
| Reasoning | No session-aware constraints, active-task re-reasoning, or downstream orchestration. |
| Interaction | The manager, dialogue policy, and command contract are planned. |
| Behavior | The executive and its command contract are planned. |
| Escort | One static simulated visitor and one task are supported; no general recovery, moving visitor, or real perception exists. |
| Navigation | The semantic adapter and Impressionism goal work; Phase 6B has one accepted custom-critic scenario. Broader destinations, pedestrian configurations, and repeatability evaluation remain future work. |
| Evaluation | A one-run functional baseline/social comparison exists; a quantitative evaluation framework remains absent. |

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
9. **Contract and state-model baseline:** added minimal person/session data,
   validated request/decision serialization, current reasoner skills, and
   ROS-independent tests.
10. **Simulated visitor session:** mapped the static Gazebo visitor marker to
    one stable track and in-memory session.
11. **Semantic navigation prototype:** filtered explicitly prepared decisions,
    sent their deterministic poses to Nav2, and reported correlated results.
12. **Minimal simulated escort:** added a public visitor-distance observation,
    four-state escort logic, intentional Nav2 pause/resume, terminal loss, and
    joint robot-plus-visitor arrival.
13. **Automated escort demo visitor:** added one opt-in scripted marker that
    creates a bounded lag-recover episode through the existing Gazebo service
    and public escort state.
14. **Simulation people stream:** mapped the three existing human markers to
    standard `/people` positions and finite-difference velocities without
    changing escort, Nav2, or DWB.
15. **Social-costmap technical prototype:** added a pinned third-party layer,
    a minimal compatibility bridge, and a separate DWB launch; integration
    checks pass, while behavioral runtime acceptance remains open.
16. **Custom proxemic DWB critic:** added direct maximum-cost scoring of DWB
    trajectories from `/people`, ignored the actively escorted visitor, and
    accepted scale 32 after a bounded four-value comparison.
17. **Text language boundary:** added deterministic Italian/English parsing,
    one-at-a-time Groq JSON translation for unresolved text, strict local
    candidate rejection, and final `StructuredRequest` validation.

This history records what was achieved while leaving interaction management,
behavior execution, generic people tracking, speech, broader social-navigation
evaluation, and real perception clearly incomplete or unimplemented.

## Revised Roadmap

| Phase | Deliverable | Completion test |
| --- | --- | --- |
| 0 | **Complete:** repository and documentation cleanup | Source-backed status and coherent architecture/roadmap. |
| 1 | **Complete:** minimal contracts and state models | Focused tests cover request validation, optional session correlation, simple session state, and deterministic reasoning. |
| 2 | **Complete:** minimal visitor session and simulated identity | Gazebo identity is converted to `PersonTrack`, then to `Session`, without leaking actor IDs downstream. |
| 3 | **Complete:** filtered reasoner -> Nav2 adapter | The prepared Impressionism request produces one correlated successful Nav2 goal; plain recommendations remain non-moving. |
| 4 | **Prototype implemented:** basic escort with simulated ground truth | Escort, wait/cancel, recover/resend, lost/cancel, and joint arrival use the static marker; normal lag/recovery is scripted and manual tests remain available. |
| 5 | **Runtime-validated prototype:** standard simulation people stream | `/people` reports the three Gazebo markers with stable public IDs and velocities while escort and DWB remain unchanged. |
| 6 | **Runtime-validated bounded prototype:** human-aware DWB trajectory critic | The custom critic runs beside an unchanged baseline, increases controlled guide clearance from 0.603 m to 0.665 m without destabilizing navigation, and preserves escort completion. |
| 7 | **Runtime-validated bounded prototype:** deterministic language parser plus Groq fallback | Offline and live functional tests pass with strict Structured Outputs and local validation; adversarial prompt-injection evaluation remains deferred. |
| 8 | faster-whisper STT | Recorded speech produces text within measured latency/resource limits. |
| 9 | Grounded answer generation and TTS | Spoken answers cite only current request/world/task facts. |
| 10 | Active-task ambient adaptation | A relevant closure/crowd update triggers controlled re-reasoning and behavior change. |
| 11 | Optional lightweight perception | Role/context cues are inferred without personal identity recognition. |
| 12 | Experimental evaluation | Repeatable metrics compare baseline and semantic/social variants. |

## Current Gate

The roadmap has passed the bounded Phase 6 gate through the custom critic. The
public people boundary is documented in `simulated_people.md`; the accepted
critic and the two earlier failed experiments are documented in
`human_aware_navigation.md`; and Phase 4 escort remains separately documented
in `social_escort.md`. Phase 7 is a runtime-validated bounded text-language
prototype; its adversarial prompt-injection evaluation remains deferred.
Real people tracking,
Interaction Management, Behavior Execution, broader human-aware evaluation,
speech, and vision remain future work.
