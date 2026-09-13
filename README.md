# Semantic Museum Guide Robot with Ambient-Aware Reasoning

Human-centered museum guide robot developed in ROS 2 Humble and Gazebo around a TIAGo platform. The system combines semantic reasoning, speech/language interfaces, visitor-session supervision, Nav2 navigation, animated human actors, and human-aware local motion.

## Project Overview

The robot receives a visitor request, converts it into a structured semantic query, reasons over a dynamic museum scene graph, resolves the selected semantic destination to a verified navigation target, and moves using Nav2. Human-aware motion is handled locally through DWB with a custom anisotropic `museum_social_critic::ProxemicForceCritic` and an explicit social-yield layer.

The architecture keeps language and reasoning separated from robot control: natural-language or LLM output is never allowed to directly generate ROS commands, arbitrary coordinates, shell commands, or executable code. Robot actions come from a fixed skill set and semantic destinations are resolved inside the robot-control boundary.

## Current System Status

The submission includes the following implemented and tested components:

- TIAGo simulation in ROS 2 Humble and Gazebo;
- supplied museum scene plus a deterministic navigation proxy and occupancy map;
- AMCL and Nav2 known-map navigation;
- dynamic semantic graph for rooms, artworks, ambient state, sessions, and requests;
- deterministic scene-graph reasoning with bounded language/LLM fallback;
- file-based speech-to-text through Groq Whisper;
- visitor-session and escort supervision;
- animated Gazebo Actors published through `/people`;
- custom anisotropic `ProxemicForceCritic` integrated into DWB;
- explicit social slow/yield/resume behavior;
- runtime monitors and reproducible demo launchers;
- benchmark and acceptance scripts for navigation, reasoning, language, social navigation, and end-to-end behavior.

The final eight-Actor social-navigation demonstration completed successfully with one navigation goal, visible slow/yield/resume behavior, and no navigation recoveries, controller aborts, failed recoveries, or acknowledgement timeouts. The demonstrated configuration uses the existing LiDAR for museum geometry and the `/people` stream for social reasoning; the tested `walk.dae` Actor asset does not produce reliable returns at the robot laser plane.

The file-based speech-to-text pipeline has also been runtime validated with a real 6-second, 16 kHz mono WAV file through `whisper-large-v3-turbo`. The validated request was transcribed as `portami a vedere qualcosa di impressionista`, parsed deterministically, and resolved by the semantic reasoner to `monet_water_lilies` in `impressionism_hall`.

## Architecture

Main runtime flow:

```text
RGB / LiDAR / simulated human state
              |
              v
        Engagement / Session
              |
              v
      Speech-to-Text (optional)
              |
              v
   Deterministic parser + bounded LLM fallback
              |
              v
        StructuredRequest
              |
              v
       Dynamic Scene Graph
              |
              v
     Deterministic Reasoner
              |
              v
      Semantic Route / Skill
              |
              v
             Nav2
              |
              v
   DWB + ProxemicForceCritic
              |
              v
     Social yield / robot motion
```

The LLM is constrained to structured language interpretation and does not control robot coordinates or actions directly.

For module boundaries and message contracts, see [Architecture](docs/architecture.md).

## Quick Start

### 1. Build the Docker image

From the repository root:

```bash
docker build -f dockerfiles/Dockerfile.tiago_museum -t museum-tiago:humble .
```

### 2. Start the interactive TIAGo container

```bash
./start_museum_tiago.sh
```

Inside the container:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant museum_social_critic museum_video1_actors
source install/setup.bash
```

## Final Demonstrations

The two commands below are the recommended entry points for the submitted project.

### Demo 1 — Eight-Actor social navigation

From a desktop terminal in the repository root:

```bash
./scripts/stop_video1_animated_demo.sh 2>/dev/null || true
./scripts/start_video1_final_animated_demo.sh --actors 8 --runtime-audit
```

This launches Gazebo, RViz, the eight animated Actors, `/people`, Nav2, the anisotropic social critic, the social-yield filter, the runtime monitor, and one navigation goal.

Stop the demo with:

```bash
./scripts/stop_video1_animated_demo.sh
```

### Demo 2 — Scene graph and semantic reasoning

```bash
./scripts/start_video2_reasoning_demo.sh
```

This launches the supplied museum scene with one Actor and shows a structured semantic request being resolved through the existing scene graph and reasoner. The prepared action is displayed but robot navigation is intentionally not started in this demo.

Stop it with:

```bash
./scripts/stop_video2_reasoning_demo.sh
```

More details are available in [Video 1 final demo](docs/video1_final_animated_demo.md) and [Video 2 reasoning demo](docs/video2_reasoning_demo.md).

## Speech-to-Text Validation

The Phase 8 file-based STT acceptance script can be run with an operator-provided WAV file:

```bash
PHASE8_SKIP_DOCKER_BUILD=1 \
./scripts/phase8_live_acceptance.sh /path/to/request.wav
```

`GROQ_API_KEY` must be available in the shell environment. The key is never stored in this repository.

The accepted interface validates the WAV, performs real transcription, publishes `/museum/user_text`, runs the existing parser, creates a `StructuredRequest`, and invokes the semantic reasoner.

## Core ROS Interfaces

Important topics include:

- `/museum/session_state`
- `/museum/engagement_state`
- `/museum/user_text`
- `/museum/user_request`
- `/museum/assistant_response`
- `/museum/navigation_result`
- `/museum/escort_state`
- `/museum/ambient_state`
- `/people`
- `/scan_raw`
- `/amcl_pose`

The social-navigation demo additionally exposes runtime diagnostic streams for Actor states, social state, and navigation measurements.

## Main Packages

### `museum_assistant`

Contains the semantic graph, reasoning, language parsing, speech-to-text interface, engagement/session logic, escort supervision, semantic navigation adapters, simulated people support, museum worlds, maps, and launch files.

### `museum_social_critic`

Custom DWB critic implementing the anisotropic proxemic cost used by the final social-navigation configuration.

### `museum_video1_actors`

Gazebo Actor support, `/people` bridging, social-yield logic, runtime auditing, and the final animated social-navigation demo.

## Social Navigation

The accepted anisotropic configuration uses directional human comfort geometry. A trajectory sample is scored from person-relative distance through a logistic cost; directional front/side/back scaling expands the effective comfort region in front of a moving person. The critic aggregates the maximum social cost over people and trajectory samples.

The final demo also uses an explicit social-yield layer for clear crossing behavior. DWB and `ProxemicForceCritic` remain active while the yield layer can slow or temporarily stop the commanded motion when a relevant human is predicted to enter the forward corridor. Once the corridor remains clear for the configured hysteresis interval, the same navigation action resumes.

For formulas, parameters, and validation evidence, see [Human-Aware Navigation](docs/human_aware_navigation.md) and [Video 1 final demo](docs/video1_final_animated_demo.md).

## Semantic Reasoning

The semantic graph represents rooms, artworks, ambient properties, sessions, and current requests. Natural-language interpretation is converted into validated structured constraints before reasoning. The reasoner then selects valid semantic entities and returns a fixed robot skill such as `navigate_to` together with a semantic destination resolved to a configured pose.

Example validated chain:

```text
"portami a vedere qualcosa di impressionista"
        -> style = impressionism
        -> monet_water_lilies
        -> impressionism_hall
        -> navigate_to
```

The separate Video 2 demo uses the request `I want to see classical art.` and resolves the existing graph fact:

```text
roman_statue : style = classical
roman_statue -> located_in -> ancient_art_hall
ancient_art_hall -> south_west_gallery
```

## Benchmarks

Benchmark data and plots are stored under `benchmarks/`.

The repository contains comparisons for:

- navigation accuracy and duration;
- semantic reasoning and language parsing;
- session memory;
- engagement and escort behavior;
- social-navigation clearance and path/time effects;
- end-to-end speech/language/reasoning episodes.

The accepted social benchmark increased controlled minimum guide clearance from approximately `0.603 m` to `0.665 m` while preserving task completion. Later animated-Actor runs validate the final social-navigation demonstration separately from those historical benchmark inputs.

See [Benchmarks](benchmarks/README.md) for methodology and raw/summary files.

## Documentation

Useful project documentation:

- [Architecture](docs/architecture.md)
- [User Manual](docs/user_manual.md)
- [Semantic Map](docs/semantic_map.md)
- [Museum Navigation](docs/museum_navigation.md)
- [Human-Aware Navigation](docs/human_aware_navigation.md)
- [Social Escort](docs/social_escort.md)
- [Speech Interface](docs/speech_interface.md)
- [Language Interface](docs/language_interface.md)
- [Video 1 Final Animated Demo](docs/video1_final_animated_demo.md)
- [Video 2 Reasoning Demo](docs/video2_reasoning_demo.md)

## Safety and Architectural Constraints

- Natural-language or LLM output may only become validated structured data.
- An LLM must never emit arbitrary ROS commands, coordinates, shell commands, or executable code for robot control.
- Robot actions come from a fixed skill set.
- Semantic location IDs are resolved to verified poses inside the robot-control boundary.
- Gazebo Actor/model identifiers do not define semantic robot actions.
- Escort supervision remains above Nav2; human-aware local motion belongs in the navigation layer.
- Simulation-specific bridges are kept explicit and separate from claims about real-world perception.

## Current Limitations

- Human state used by the final animated social-navigation demo comes from simulation `/people` data rather than a generic real-world people tracker.
- The tested `walk.dae` Actor configuration is not reliably visible in the TIAGo LiDAR plane; LiDAR is still used for museum geometry.
- Not every configured semantic room pose has the same level of runtime acceptance as the main demonstrated routes.
- The current speech interface is file based; microphone streaming and text-to-speech are not part of the submitted runtime.
- The project is a simulation research prototype, not a certified safety system.

## Future Work

1. Replace simulation-assisted people state with a generic perception/tracking pipeline.
2. Improve multimodal engagement across RGB, LiDAR, speech activity, and gaze.
3. Add grounded spoken responses through text-to-speech.
4. Extend scene-graph user memory and persistent interaction sessions.
5. Re-reason dynamically when crowd, noise, or room availability changes during a task.
6. Evaluate the system with a larger set of users and social scenarios.
