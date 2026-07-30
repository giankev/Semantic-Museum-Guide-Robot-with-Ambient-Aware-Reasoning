# System Architecture

## Purpose And Status

This document defines the module boundaries for the Semantic Museum Guide Robot. It distinguishes the code that exists now from the intended architecture so that planned modules are not mistaken for working features.

Status labels used below:

- **Implemented:** source and launch/configuration are present, with an existing validated milestone.
- **Prototype:** source exists and is demonstrable, but it is scripted, manual, isolated, or not production-connected.
- **Planned:** no runtime implementation exists.

## Current Architecture

The current repository correlates one simulated visitor session through
structured reasoning and a focused semantic-navigation prototype.

```text
visitor_marker -> Gazebo model states -> visitor_session_node
                                      -> /museum/session_state
                                      -> user_request_simulator
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
                                      |
                                      v
                   Nav2 NavigateToPose -> DWB -> TIAGo base
                                      |
                                      v
                         /museum/navigation_result
```

Important current properties:

- `reasoning_node` owns its own in-memory `MuseumSemanticGraph`.
- `semantic_graph_node` also owns a separate in-memory graph when launched. The two processes do not share state.
- `ambient_reasoning.launch.py` demonstrates ambient updates with `semantic_graph_node`.
- `reasoning_demo.launch.py` demonstrates ambient updates and requests with `reasoning_node`.
- `semantic_navigation_node` is the only navigation consumer of
  `/museum/assistant_response`; Interaction Manager, Behavior Executive, and
  escort remain unimplemented.
- `send_nav_goal` accepts raw coordinates from a developer CLI. It is a test helper, not a semantic navigation executor.
- Nav2 uses the standard DWB local planner. There is no people layer or human-aware controller.
- The visual visitor, guide, and staff models in `museum.world` remain static.
  Only `visitor_marker` is used as simulation ground truth for one session; it
  is not real person perception or tracking.
- `visitor_session_node` keeps the Gazebo model name internal and publishes
  only `session_id`, `track_id`, and state on `/museum/session_state`.
- The Phase 2 session is minimal and in memory. It has no preferences, history,
  task state, persistence, or disappearance/re-identification behavior.

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
| Perception | Detect/track an engaged person and publish transient robot-centric observations. | Simulation-ground-truth prototype | `visitor_session_node` observes static `visitor_marker` through Gazebo model states and maps it internally to `visitor_1`; no real perception exists. |
| Session | Map a transient track to a visitor interaction session and own session lifecycle. | Minimal runtime implemented | One in-memory active `SessionState` named `session_1` is created and reused for `visitor_1`. |
| Language | Convert speech/text into a validated structured request. | Contract and structured-topic prototype implemented | `StructuredRequest` validates `/museum/user_request`; no text parser, LLM, or STT exists. |
| Semantic World Model | Represent persistent museum knowledge and dynamic contextual facts. | Implemented for museum and ambient facts; planned for people/session/task facts | `semantic_map.yaml`, `semantic_graph.py`, in-memory room updates. |
| Reasoning | Select a destination/alternative from validated constraints and explain the choice. | Implemented deterministic baseline and typed boundary | `reasoning.py` consumes `StructuredRequest` and produces `ReasoningDecision`. |
| Interaction Management | Own dialogue and task progression, clarification, confirmation, and visitor-facing responses. | Planned | No manager, dialogue policy, or command contract exists. |
| Behavior Execution | Validate and dispatch only whitelisted robot skills. | Planned | The reasoner has a small `Skill` enum for its current outputs; no behavior command or executive exists. |
| Escort | Decide whether a guidance task is socially succeeding and coordinate pause/recovery/cancel behavior. | Planned | No escort state model or supervisor exists. |
| Navigation | Localize, plan, control, and execute a verified goal. | Semantic execution prototype implemented | `semantic_navigation_node` sends approved deterministic poses to `NavigateToPose` and publishes JSON results; runtime calibration and acceptance remain. |

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

Ambient room state and one minimal in-memory visitor session are implemented.
Preferences, task state, persistence, and escort facts remain planned.

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

In Phase 2, `visitor_session_node` is this boundary: it observes
`visitor_marker`, maps it to `visitor_1`, and publishes the in-memory
`session_1`. The Gazebo name is not present in `/museum/session_state`,
structured requests, or reasoning responses. A future perception system can
replace the simulation-ground-truth input without changing those public IDs.

## Phase 2 Simulated Visitor Session

The museum world loads the standard Gazebo ROS state plugin at 1 Hz.
`visitor_session_node` subscribes to `/gazebo/model_states` and checks only for
the existing static `visitor_marker`. Its mapping is intentionally fixed and
small:

```text
visitor_marker (node-internal) -> visitor_1 -> session_1 (active)
```

The session is stored only in process memory and reused on every observation.
`/museum/session_state` is periodically republished as JSON so a newly started
demo terminal can observe it. The request simulator caches the active
`session_id` and adds it to subsequent structured requests; the unchanged
reasoner copies it into `/museum/assistant_response`.

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

## Phase 3 Semantic Navigation Prototype

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

Only one goal may be active. A boolean is set before contacting Nav2 and
cleared after server failure, rejection, success, abort, or cancellation.
Additional decisions are ignored while it is set; there is no queue,
preemption, recovery policy, Interaction Manager, or Behavior Executive.

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

Nav2 retains responsibility for its standard planning and recovery behavior.
The semantic poses remain a calibration dependency, so this layer is classified
as a prototype until the complete simulator acceptance workflow succeeds.

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

It belongs in or beside the Nav2 local-planning layer. DWB remains the baseline for comparison when a human-aware controller or people-aware costmap is added.

## Language And Robot-Control Safety

- Speech/text parsing ends in a schema-validated request.
- Deterministic code selects actions from a fixed skill set.
- Neither an LLM nor user text may produce executable ROS commands, shell commands, Python, or raw navigation coordinates.
- Unknown intents, constraints, locations, sessions, or skills must fail closed with clarification or a safe no-op.
- Explanations must be grounded in the selected semantic facts and actual task result.

## Phase Boundaries

The development sequence is intentionally incremental. Phases 1 and 2 are
complete; Phase 3 is implemented as a prototype pending runtime acceptance:

1. **Complete:** define interfaces and state ownership.
2. **Complete:** add one in-memory session using simulated identity ground truth.
3. **Prototype:** connect explicitly prepared deterministic decisions directly
   to Nav2 without introducing future task-management layers.
4. **Not started:** add escort supervision with simulation ground truth.
5. Generalize people tracking.
6. Add human-aware local navigation.
7. Add natural-language parsing.
8. Add speech-to-text.
9. Add grounded answers and speech output.
10. Add active-task ambient adaptation.
11. Optionally add lightweight perception.
12. Run comparative evaluation.

No later phase should bypass the interfaces and safety boundaries established by earlier phases.
