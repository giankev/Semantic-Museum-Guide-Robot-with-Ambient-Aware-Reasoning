# System Architecture

## Purpose And Status

This document defines the module boundaries for the Semantic Museum Guide Robot. It distinguishes the code that exists now from the intended architecture so that planned modules are not mistaken for working features.

Status labels used below:

- **Implemented:** source and launch/configuration are present, with an existing validated milestone.
- **Prototype:** source exists and is demonstrable, but it is scripted, manual, isolated, or not production-connected.
- **Planned:** no runtime implementation exists.

## Current Architecture

The current repository correlates one simulated visitor session through
structured reasoning, semantic navigation, and minimal escort supervision.

```text
visitor_marker -> Gazebo model states -> visitor_session_node
                                      -> /museum/session_state
                                      -> /museum/visitor_observation
                                      -> language_node session correlation
                                                   |
/museum/user_text -> deterministic parser -> optional Groq fallback
                                                   |
                                      -> /museum/user_request
                                                  |
semantic_map.yaml --------------------+           |
                                      |           v
/museum/ambient_state ----------> reasoning_node <- /museum/user_request
  scripted JSON                 in-memory graph      structured JSON
                                      |
                                      v
                           /museum/assistant_response
                           session_id + selected_room +
                           skill + nav_pose + explanation
                                      |
                                      v
                         semantic_navigation_node
                          escort.py state logic
                              |             |
                              v             v
                 /museum/escort_state   Nav2 NavigateToPose
                                             |
                                             v
                                      DWB -> TIAGo base
                                             |
                                             v
                                /museum/navigation_result

Optional demo-only simulation sidecar:
/museum/escort_state + Gazebo model states
                  -> scripted_visitor_node
                  -> /gazebo/set_entity_state -> visitor_marker

Optional Phase 5/6 social sidecar:
Gazebo model states -> simulated_people_node
                    -> /people (social_nav_msgs/Pedestrians)
                       |-> ProxemicForceCritic -> DWB (accepted Phase 6B)
                       `-> social_people_bridge_node
                           -> /people_nav2 (people_msgs/People)
                           -> UPO social local-costmap layer -> DWB
                              (earlier behavior-failed experiment)
```

Important current properties:

- `reasoning_node` owns its own in-memory `MuseumSemanticGraph`.
- `semantic_graph_node` also owns a separate in-memory graph when launched. The two processes do not share state.
- `ambient_reasoning.launch.py` demonstrates ambient updates with `semantic_graph_node`.
- `reasoning_demo.launch.py` demonstrates ambient updates and requests with `reasoning_node`.
- `semantic_navigation_node` is the only navigation consumer of
  `/museum/assistant_response` and the only owner of the current
  `NavigateToPose` goal. Interaction Manager and Behavior Executive remain
  unimplemented.
- `send_nav_goal` accepts raw coordinates from a developer CLI. It is a test helper, not a semantic navigation executor.
- The unchanged baseline Nav2 launch uses the standard DWB local planner and
  no people layer. One separate opt-in launch retains the earlier UPO social
  layer experiment. The accepted Phase 6B launch instead keeps the baseline
  obstacle/inflation local costmap and adds a custom DWB trajectory critic that
  consumes `/people` directly.
- `simulated_people_node` publishes the existing visitor, guide, and staff
  markers on standard `/people` data with stable public IDs and
  finite-difference velocities. The optional compatibility bridge consumes
  that topic only for the third-party social layer; escort does not.
- The visual visitor, guide, and staff models in `museum.world` remain static
  Gazebo models. The opt-in `scripted_visitor_node` can reposition only
  `visitor_marker` for the lag-recovery demo. It is still simulation ground
  truth, not real person perception, tracking, or autonomy.
- `visitor_session_node` keeps the Gazebo model name internal and publishes
  session state plus a public present/distance observation. Neither public JSON
  topic contains Gazebo model names.
- The Phase 2 session is minimal and in memory. It has no preferences, history,
  task state, persistence, or disappearance/re-identification behavior.
- `escort.py` provides four states for one task. It can request an intentional
  cancel/resend through the existing semantic-navigation node, but it does not
  control local motion or alter DWB.

## Target Architecture

```text
Human
  |
  v
Person / Engagement Perception
  |  PersonTrack ID
  v
Session Manager
  |  Session ID + interaction context
  v
Speech-to-Text
  |
  v
Natural-Language / Structured Request Parser
  |  validated request JSON
  v
Semantic Graph / World Model <------ ambient state and task/session facts
  |
  v
Deterministic Semantic Reasoner
  |  decision + explanation + abstract skill
  v
Interaction Manager
  |  dialogue/task transition
  v
Behavior Executive
  |  whitelisted behavior command
  v
Social Escort Supervisor <---------- tracked visitor/session state
  |  navigation command / pause / recovery / cancel
  v
Nav2
  |
  v
Human-aware Local Navigation
  |
  v
TIAGo
```

The arrows show the main control flow, not a requirement that every module be a separate ROS 2 node. Small modules should remain plain Python when a node provides no clear runtime benefit.

## Module Responsibilities

| Layer | Responsibility | Current status | Current artifact or future boundary |
| --- | --- | --- | --- |
| Perception | Detect/track an engaged person and publish transient robot-centric observations. | Simulation-ground-truth adapters only | `visitor_session_node` publishes visitor presence/distance for escort; `simulated_people_node` publishes three Gazebo markers on standard `/people`. No real perception or tracking exists. |
| Session | Map a transient track to a visitor interaction session and own session lifecycle. | Minimal runtime implemented | One in-memory active `SessionState` named `session_1` is created and reused for `visitor_1`. |
| Language | Convert speech/text into a validated structured request. | Text prototype implemented; offline accepted, live Groq pending | `language_node` parses `/museum/user_text` deterministically, uses Groq only for unresolved text, validates locally, then constructs `StructuredRequest`. No STT exists. |
| Semantic World Model | Represent persistent museum knowledge and dynamic contextual facts. | Implemented for museum and ambient facts; planned for people/session/task facts | `semantic_map.yaml`, `semantic_graph.py`, in-memory room updates. |
| Reasoning | Select a destination/alternative from validated constraints and explain the choice. | Implemented deterministic baseline and typed boundary | `reasoning.py` consumes `StructuredRequest` and produces `ReasoningDecision`. |
| Interaction Management | Own dialogue and task progression, clarification, confirmation, and visitor-facing responses. | Planned | No manager, dialogue policy, or command contract exists. |
| Behavior Execution | Validate and dispatch only whitelisted robot skills. | Planned | The reasoner has a small `Skill` enum for its current outputs; no behavior command or executive exists. |
| Escort | Decide whether a guidance task is socially succeeding and coordinate pause/recovery/cancel behavior. | Minimal simulation-ground-truth prototype | `escort.py` implements `ESCORTING`, `WAITING`, `LOST`, and `ARRIVED`; `semantic_navigation_node` performs intentional pause/resume for one task. The opt-in scripted marker is demo infrastructure, not escort intelligence. |
| Navigation | Localize, plan, control, and execute a verified goal. | Semantic execution and bounded Phase 6B human-aware behavior accepted | `semantic_navigation_node` sends approved deterministic poses to `NavigateToPose`; baseline Nav2/AMCL/NavFn/DWB remain unchanged. The accepted opt-in variant adds `ProxemicForceCritic` to DWB and consumes `/people` directly; the earlier UPO-layer variant remains a behavior-failed experiment. |

## Phase 5 Simulation People Boundary

`simulated_people_node` is an opt-in Gazebo adapter. It maps
`visitor_marker`, `guide_marker`, and `staff_marker` to stable public IDs and
publishes `social_nav_msgs/msg/Pedestrians` on `/people`. Position is copied
from the verified world/map-aligned x/y coordinates; velocity is estimated
from consecutive positions using ROS simulation time.

This remains the project's standard people boundary. The existing escort still
consumes `/museum/visitor_observation`. The accepted Phase 6B critic consumes
`/people` directly and ignores the escorted `visitor_1`; the independent escort
supervisor continues to own visitor-following state. The compatibility bridge
to `/people_nav2` remains only for the earlier third-party SocialLayer
experiment. DWB remains the controller in every variant. See
[Simulated People](simulated_people.md) for the public schema and
[Human-Aware Navigation](human_aware_navigation.md) for runtime evidence.

## Semantic World Model

The future world model must contain two kinds of knowledge.

### Persistent Knowledge

- rooms and museum topology;
- artworks, styles, periods, and semantic tags;
- accessibility and suitability properties;
- semantic location IDs and verified navigation poses;
- sensor-to-room associations;
- roles and allowed domain actions.

Most of this is already represented in `config/semantic_map.yaml`. The graph currently stores `connected_to` edges as directed relations because it uses `nx.DiGraph`; code that needs bidirectional topology must either encode reverse edges or define explicit traversal semantics.

### Dynamic Knowledge

- ambient room status, crowd, and noise;
- transient person tracks;
- interaction sessions and preferences;
- current destination and active task;
- escort status and relevant interaction facts;
- navigation/task outcomes.

Ambient room state, one minimal in-memory visitor session, and transient escort
state for one task are implemented. Preferences and persistence remain planned.

## Identity Abstraction

Simulation-specific identity must stop at the perception adapter. The track and
session identifiers are ordinary validated strings, not wrapper classes:

```text
Gazebo actor/model ID -> PersonTrack ID -> Session ID
```

A future real deployment substitutes its detector/tracker on the left:

```text
detector/tracker -> PersonTrack ID -> Session ID
```

In Phases 2 and 4, `visitor_session_node` is this boundary: it observes the
configured simulator models, maps the visitor to `visitor_1`, and publishes the
in-memory `session_1` plus a planar distance observation. Gazebo names are not
present in `/museum/session_state`, `/museum/visitor_observation`, structured
requests, reasoning responses, or escort state.

## Phase 2 Simulated Visitor Session

The museum world loads the standard Gazebo ROS state plugin at 1 Hz.
`visitor_session_node` subscribes to `/gazebo/model_states` and observes the
existing static visitor plus TIAGo. Its simulation-only model-name parameters
default to the runtime-verified `visitor_marker` and `tiago`; its public mapping
remains intentionally fixed and small:

```text
visitor_marker (node-internal) -> visitor_1 -> session_1 (active)
```

The session is stored only in process memory and reused on every observation.
`/museum/session_state` is periodically republished as JSON so a newly started
demo terminal can observe it. The request simulator caches the active
`session_id` and adds it to subsequent structured requests; the unchanged
reasoner copies it into `/museum/assistant_response`.

Phase 4 also publishes `/museum/visitor_observation` with `session_id`,
`track_id`, `present`, and `distance_to_robot` when available. This is simulator
ground truth, not a generic tracked-person contract.

The static marker is not a moving person, actor, tracker, engagement signal, or
identity-perception system. Session closure on disappearance is deferred until
the project introduces a reliable lifecycle requirement.

## Phase 1 Contract Boundaries

Phase 1 implements and tests these ROS-independent contracts in
`museum_assistant/contracts.py`:

| Contract | Minimum content | Producer | Consumer |
| --- | --- | --- | --- |
| `PersonTrack` | `track_id` string | Perception adapter | Session Manager |
| `SessionState` | `session_id`, `track_id`, and lifecycle value | Session Manager | Session Manager |
| `StructuredRequest` | `request_id`, `session_id`, supported intent, validated constraints | Language | Reasoner |
| `ReasoningDecision` | current response status, semantic room, skill, reason, compatibility fields | Reasoner | Current JSON response topic |
| `Skill` | `navigate_to` or `ask_clarification` | Reasoner | Current JSON response topic |

The Phase 3 adapter temporarily uses the current `nav_pose` in
`ReasoningDecision`, which is produced deterministically from the selected
semantic room. These poses must be verified against the occupancy map. A later
architecture may resolve semantic locations at the navigation boundary, but no
additional graph or navigation-result contract is introduced in Phase 3.

## Phase 3 Semantic Navigation

`semantic_navigation_node` subscribes to `/museum/assistant_response`. It sends
a `map`-frame `NavigateToPose` goal only when all three conditions match:

```text
status = success
skill = navigate_to
intent = recommend_and_prepare_navigation
```

Plain `recommend` decisions, no-match results, clarification requests, and
malformed poses do not move TIAGo. The adapter validates finite numeric `x`,
`y`, and `yaw`, then uses the deterministic pose already present in the
reasoning response.

Only one semantic escort/navigation task may be active. Additional executable
decisions are ignored until it becomes terminal; there is no queue, priority,
preemption system, Interaction Manager, or Behavior Executive.

`/museum/navigation_result` is JSON over `std_msgs/String`. It carries available
`request_id`, `session_id`, and `selected_room` correlation fields plus one of:

```text
accepted
succeeded
aborted
canceled
rejected
server_unavailable
```

Nav2 retains responsibility for planning, recovery, and local control. The full
Phase 3 chain passed runtime acceptance for `impressionism_hall`; other semantic
poses remain individual calibration dependencies.

## Phase 4 Minimal Escort Prototype

`escort.py` is a ROS-independent state machine with only `ESCORTING`, `WAITING`,
`LOST`, and `ARRIVED`. Before a task starts it is inactive. The semantic
navigation node feeds it public visitor observations and remains the sole Nav2
action owner.

When lag beyond `wait_distance` persists for `wait_delay`, the state becomes
`WAITING` and the node intentionally cancels the active Nav2 goal. That canceled
result remains visible on `/museum/navigation_result`, but a small internal
pause marker keeps the semantic task alive. Recovery below `resume_distance`
resends the same stored pose. A cancellation without that pause marker is
terminal. `LOST` cancels if necessary and never auto-recovers.

Nav2 `succeeded` does not complete the escort. The state becomes `ARRIVED` only
when the visitor is present within `arrival_distance`. Otherwise it remains
`WAITING` at the stopped destination until the visitor arrives, with no goal
resend. `/museum/escort_state` publishes the current public state, correlation
fields, and the available distance. See [Social Escort](social_escort.md) for
the exact schemas and runtime procedure.

The optional `scripted_visitor_node` makes the normal lag-recovery episode
repeatable without manual marker teleports. It reads the same public escort
state plus Gazebo model poses and uses the Gazebo state service for bounded
planar marker motion. It neither publishes an escort decision nor controls
TIAGo. Its direct following has no path planning or obstacle avoidance, and
the original manual test remains available whenever the node is not launched.

## Social Escort Versus Social Navigation

These are separate control concerns.

### Social Escort

The Escort Supervisor sits above Nav2 and answers questions such as:

- Is the visitor still following?
- Has the visitor stopped or fallen behind?
- Is the visitor lost?
- Was contact recovered?
- Did both robot and visitor reach the destination?

It may pause, wait, request recovery behavior, cancel navigation, or report task completion. It does not implement local obstacle avoidance.

### Social Navigation

Social navigation controls how the robot moves around people:

- proxemic distance;
- passing behavior;
- human-aware costs;
- local velocity/path choices.

It belongs in or beside the Nav2 local-planning layer. DWB remains the unchanged
baseline and the controller used by the accepted human-aware variant.

The earlier opt-in `nav2_social_costmap_plugin::SocialLayer` prototype
generated non-zero costs but measured only `0.603 m` baseline versus `0.604 m`
social clearance, so that variant remains behavior-failed. Phase 6B instead
adds `museum_social_critic::ProxemicForceCritic`, which applies a bounded
maximum proxemic cost directly to predicted DWB trajectory/person encounters.
At the selected scale 32, the same controlled scenario succeeded with 0.665 m
minimum clearance, a 0.062 m or 10.3% increase over baseline, while preserving
the automatic escort sequence. This is a small proxemic/social-force-inspired
critic, not the full Helbing model, Social MPC, or learned prediction.

## Language And Robot-Control Safety

- Speech/text parsing ends in a schema-validated request.
- Deterministic code selects actions from a fixed skill set.
- Neither an LLM nor user text may produce executable ROS commands, shell commands, Python, or raw navigation coordinates.
- Unknown intents, constraints, locations, sessions, or skills must fail closed with clarification or a safe no-op.
- Explanations must be grounded in the selected semantic facts and actual task result.

## Phase Boundaries

The development sequence is intentionally incremental. Phases 1 through 3 are
complete, Phases 4 and 5 are constrained validated prototypes, and Phase 6 is
runtime-validated through the bounded custom-critic result:

1. **Complete:** define interfaces and state ownership.
2. **Complete:** add one in-memory session using simulated identity ground truth.
3. **Complete:** connect explicitly prepared deterministic decisions directly
   to Nav2 and pass the runtime acceptance chain.
4. **Prototype implemented:** supervise one simulated visitor with
   simulator-ground-truth pause/resume/lost/arrival scenarios; the normal
   lag-recovery demo can be scripted, while manual testing remains available.
5. **Runtime-validated prototype:** publish the current Gazebo human markers
   on a standard `/people` stream without changing escort or baseline
   navigation.
6. **Runtime-validated bounded prototype:** directly score DWB trajectories
   from `/people` using the custom proxemic critic while preserving the
   baseline and the independent escort supervisor. The earlier generic
   SocialLayer and Phase 6A tuning results remain documented failures.
7. **Implemented; offline accepted and live Groq pending:** add deterministic
   text parsing with a strict Groq fallback boundary.
8. Add speech-to-text.
9. Add grounded answers and speech output.
10. Add active-task ambient adaptation.
11. Optionally add lightweight perception.
12. Run comparative evaluation.

No later phase should bypass the interfaces and safety boundaries established by earlier phases.
