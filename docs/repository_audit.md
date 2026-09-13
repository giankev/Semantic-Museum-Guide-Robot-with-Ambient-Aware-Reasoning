# Repository Audit — Submission State

This document summarizes the implementation boundaries of the submitted ROS 2 / Gazebo museum-guide project.

## Implemented Runtime Components

The repository contains three main ROS 2 packages used by the final demonstrations:

- `museum_assistant` — semantic graph, deterministic reasoning, language parsing, file-based speech-to-text, session/engagement logic, escort supervision, semantic navigation, museum worlds and maps;
- `museum_social_critic` — custom anisotropic DWB proxemic critic;
- `museum_video1_actors` — animated Gazebo Actors, `/people` bridge, social-yield behavior, runtime auditing, and final social-navigation launch support.

The submitted system has runtime evidence for semantic reasoning, file-based STT, Nav2 navigation, social navigation, and the final eight-Actor demonstration. Simulation-specific human state is explicitly separated from claims about real-world perception.

## Control Boundary

The project maintains a strict separation between language/semantic reasoning and robot actuation:

```text
speech/text
   -> validated structured request
   -> semantic graph / deterministic reasoner
   -> fixed skill + semantic destination
   -> configured navigation pose
   -> Nav2
```

Natural-language or LLM output is not allowed to emit arbitrary robot coordinates, ROS commands, shell commands, or executable code.

## Semantic Graph and Reasoning

The graph represents rooms, artworks, ambient attributes, current sessions, and requests. The reasoner filters candidates according to structured constraints and ambient state, then selects a fixed skill such as `navigate_to`.

The final Video 2 reasoning demo uses the structured request corresponding to `I want to see classical art.` and resolves the existing graph to `roman_statue`, `ancient_art_hall`, and the configured `south_west_gallery` route.

## Speech and Language

The project includes:

- deterministic language parsing for supported request patterns;
- bounded LLM fallback for language interpretation;
- file-based speech-to-text through the configured Groq Whisper endpoint;
- validation of input audio format and negative cases;
- publication of the normalized transcript to the existing language interface.

The live Phase 8 acceptance was executed with a real 6-second mono 16 kHz WAV file and `whisper-large-v3-turbo`. The transcript `portami a vedere qualcosa di impressionista` was converted into a deterministic structured request and successfully resolved to the Impressionism destination.

Microphone streaming and text-to-speech are not part of the submitted runtime.

## Navigation

Nav2 provides global planning, local DWB control, behavior-tree navigation, and AMCL localization. The supplied museum is used through a deterministic navigation proxy and occupancy map designed for repeatable simulation navigation while preserving the visual supplied scene.

The final social-navigation demo uses the target:

```text
(0.0, 16.0, 1.5708)
```

and sends one `NavigateToPose` goal.

## Human-Aware Navigation

The custom plugin:

```text
museum_social_critic::ProxemicForceCritic
```

scores DWB candidate trajectories from `/people` using a logistic proxemic cost and directional front/side/back geometry. Human state is projected across candidate trajectory time and the maximum social cost is aggregated across people and samples.

The final animated demo also uses a social-yield filter for explicit slowdown/stop/resume behavior during relevant crossings. This filter does not replace DWB or the proxemic critic.

## Actor / LiDAR Boundary

A controlled experiment with the exact final `walk.dae` Actor asset and TIAGo GPU-LiDAR configuration found no reliable Actor returns at the robot laser plane, while positive box controls were detected.

Therefore:

- LiDAR remains active for museum geometry;
- animated people are supplied to the social-navigation layer through `/people`;
- the project does not claim generic LiDAR detection of the final Actor mesh.

This is a simulation-specific result and is not generalized beyond the tested setup.

## Final Social-Navigation Runtime Evidence

The final eight-Actor GUI run reached navigation success and demonstrated moving/slow/stop/resume behavior with:

```text
NavigateToPose goals:          1
Minimum human center distance: 0.782 m
Recoveries:                    0
Invalid trajectories:          0
Controller aborts:             0
Failed recoveries:             0
Acknowledgement timeouts:      0
Observed RTF:                  0.396
```

The recorder's aggregate people-frequency flag was not satisfied for every observed sample in that run, so the repository does not claim a perfect all-checks-pass aggregate. The physical run nevertheless completed successfully and visibly demonstrated the intended social behavior.

## Escort Supervision

Escort supervision remains above Nav2. The state machine can publish:

```text
ESCORTING
WAITING
LOST
ARRIVED
```

When a visitor falls too far behind, the current implementation may cancel the active navigation goal and later reissue the same semantic destination when the visitor returns within the resume threshold. This behavior is documented rather than hidden.

## Simulation Versus Real-World Claims

The following inputs are simulation-assisted in the submitted demonstrations:

- Gazebo Actor positions and velocities used for `/people`;
- ground-truth visitor state used by some engagement/escort test workflows;
- simulated ambient room state used by ambient-reasoning demos.

The project therefore demonstrates the robotics/AI architecture and behavior in simulation, not a production-ready real-world perception stack.

## Main Reproduction Commands

Final social-navigation demo:

```bash
./scripts/stop_video1_animated_demo.sh 2>/dev/null || true
./scripts/start_video1_final_animated_demo.sh --actors 8 --runtime-audit
```

Scene-graph reasoning demo:

```bash
./scripts/start_video2_reasoning_demo.sh
```

File-based STT acceptance:

```bash
PHASE8_SKIP_DOCKER_BUILD=1 \
./scripts/phase8_live_acceptance.sh /path/to/request.wav
```

## Known Limitations

- generic real-world people tracking is not part of the final animated demo;
- the speech interface is file based rather than microphone streaming;
- TTS is not implemented;
- not all configured semantic room poses have identical runtime acceptance depth;
- the project is a university simulation prototype and not a certified safety system.
