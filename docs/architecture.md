# System Architecture

## Purpose And Status

This document defines the module boundaries for the Semantic Museum Guide Robot. It distinguishes the code that exists now from the intended architecture so that planned modules are not mistaken for working features.

Status labels used below:

- **Implemented:** source and launch/configuration are present, with an existing validated milestone.
- **Prototype:** source exists and is demonstrable, but it is scripted, manual, isolated, or not production-connected.
- **Planned:** no runtime implementation exists.

## Current Architecture

The current repository contains a semantic/reasoning path and a navigation path, but no runtime component connects them.

```text
semantic_map.yaml --------------------+
                                      |
/museum/ambient_state ----------> reasoning_node <---------- /museum/user_request
  scripted JSON                 in-memory graph                 scripted/manual JSON
                                      |
                                      v
                           /museum/assistant_response
                           selected_room + skill +
                           nav_pose + explanation
                                      |
                                no consumer

museum.world -> TIAGo -> scan/odom/TF -> AMCL + Nav2 -> DWB -> TIAGo base
                                             ^
                                             |
                              RViz/manual action/send_nav_goal
```

Important current properties:

- `reasoning_node` owns its own in-memory `MuseumSemanticGraph`.
- `semantic_graph_node` also owns a separate in-memory graph when launched. The two processes do not share state.
- `ambient_reasoning.launch.py` demonstrates ambient updates with `semantic_graph_node`.
- `reasoning_demo.launch.py` demonstrates ambient updates and requests with `reasoning_node`.
- `/museum/assistant_response` has no implemented interaction, behavior, escort, or navigation consumer.
- `send_nav_goal` accepts raw coordinates from a developer CLI. It is a test helper, not a semantic navigation executor.
- Nav2 uses the standard DWB local planner. There is no people layer or human-aware controller.
- The visual visitor, guide, and staff models in `museum.world` are static markers, not tracked people or sessions.
- Phase 1 contract classes exist independently of ROS, but none of the future
  runtime managers or adapters have been implemented.

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
| Perception | Detect/track an engaged person and publish transient robot-centric observations. | Contract implemented; runtime planned | `PersonTrackId` and `PersonTrack` exist. A future simulation adapter may read Gazebo actor/model state, but only emits track IDs downstream. |
| Session | Map a transient track to a visitor interaction session and own session lifecycle. | Contract implemented; runtime planned | Typed session IDs, state, and lifecycle transitions exist; no Session Manager exists. |
| Language | Convert speech/text into a validated structured request. | Contract and structured-topic prototype implemented | `StructuredRequest` validates `/museum/user_request`; no text parser, LLM, or STT exists. |
| Semantic World Model | Represent persistent museum knowledge and dynamic contextual facts. | Implemented for museum and ambient facts; planned for people/session/task facts | `semantic_map.yaml`, `semantic_graph.py`, in-memory room updates. |
| Reasoning | Select a destination/alternative from validated constraints and explain the choice. | Implemented deterministic baseline and typed boundary | `reasoning.py` consumes `StructuredRequest` and produces `ReasoningDecision`. |
| Interaction Management | Own dialogue and task progression, clarification, confirmation, and visitor-facing responses. | Contract implemented; runtime planned | `InteractionCommand` exists; no manager or dialogue policy exists. |
| Behavior Execution | Validate and dispatch only whitelisted robot skills. | Contract implemented; runtime planned | `BehaviorCommand` accepts only `navigate_to(semantic_target)` or `ask_clarification(question)`; no executive exists. |
| Escort | Decide whether a guidance task is socially succeeding and coordinate pause/recovery/cancel behavior. | State enum implemented; runtime planned | `EscortState` values exist; no supervisor or transitions exist. |
| Navigation | Localize, plan, control, and execute a verified goal. | Geometric baseline and result contract implemented; semantic execution planned | Saved map, AMCL, Nav2, DWB, manual helper, and `NavigationResult`; no semantic executor. |

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

Only ambient room state is currently implemented, and it is process-local and non-persistent. Visitor, session, task, and escort facts are planned.

## Identity Abstraction

Simulation-specific identity must stop at the perception adapter:

```text
Gazebo actor/model ID -> PersonTrack ID -> Session ID
```

A future real deployment substitutes its detector/tracker on the left:

```text
detector/tracker -> PersonTrack ID -> Session ID
```

Reasoning, interaction, behavior, and escort code must not depend on Gazebo names or future detector-specific IDs. A `PersonTrack` may be short-lived or replaced; a `Session` is the interaction-level identity and owns preferences and task context.

## Phase 1 Contract Boundaries

Phase 1 implements and tests these ROS-independent contracts in
`museum_assistant/contracts.py`:

| Contract | Minimum content | Producer | Consumer |
| --- | --- | --- | --- |
| `PersonTrack` | typed `track_id` and observation timestamp | Perception adapter | Session Manager, Escort |
| `SessionState` | typed `session_id`, current `track_id`, and explicit lifecycle | Session Manager | Language, World Model, Interaction Manager, Escort |
| `StructuredRequest` | `request_id`, `session_id`, supported intent, validated constraints | Language | Reasoner |
| `ReasoningDecision` | status, selected semantic location, abstract skill, reason, rejected alternatives | Reasoner | Interaction Manager |
| `InteractionCommand` | request/session correlation plus an approved semantic action | Interaction Manager | Behavior Executive |
| `BehaviorCommand` | whitelisted skill plus semantic target or clarification question | Behavior Executive | Escort or Navigation adapter |
| `EscortState` | following/stopped/lagging/lost/recovered/arrived values | Escort Supervisor | Interaction Manager, Behavior Executive |
| `NavigationResult` | semantic target, result status, and optional session | Navigation adapter | Escort, Behavior Executive, World Model |

The current `nav_pose` in `ReasoningDecision` is useful for the prototype and debugging. In the target design, the Behavior/Navigation boundary should resolve the selected semantic location to the latest verified pose rather than trusting coordinates from language input or an external model.

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

The development sequence is intentionally incremental. Phase 1 is complete;
Phase 2 is next:

1. **Complete:** define interfaces and state ownership.
2. **Next:** add sessions and simulated identity abstraction.
3. Connect reasoner, interaction, behavior, and Nav2.
4. Add escort supervision with simulation ground truth.
5. Generalize people tracking.
6. Add human-aware local navigation.
7. Add natural-language parsing.
8. Add speech-to-text.
9. Add grounded answers and speech output.
10. Add active-task ambient adaptation.
11. Optionally add lightweight perception.
12. Run comparative evaluation.

No later phase should bypass the interfaces and safety boundaries established by earlier phases.
