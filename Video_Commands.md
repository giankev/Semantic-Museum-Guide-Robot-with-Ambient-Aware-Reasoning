# Demo Commands

Run these commands from the repository root on the Ubuntu host.

## Build the Docker image

```bash
docker build -f dockerfiles/Dockerfile.tiago_museum -t museum-tiago:humble .
```

## Final social-navigation demo

The submitted social-navigation demo uses eight animated Gazebo Actors, Nav2, the custom anisotropic `ProxemicForceCritic`, the social-yield layer, Gazebo, RViz, and the runtime monitor.

Start:

```bash
./scripts/stop_video1_animated_demo.sh 2>/dev/null || true
./scripts/start_video1_final_animated_demo.sh --actors 8 --runtime-audit
```

Stop:

```bash
./scripts/stop_video1_animated_demo.sh
```

The launcher sends one navigation goal automatically. No manual ROS publication is required for the recorded demo.

## Scene-graph reasoning demo

Start:

```bash
./scripts/start_video2_reasoning_demo.sh
```

Stop:

```bash
./scripts/stop_video2_reasoning_demo.sh
```

This demo uses one Actor and executes the existing semantic graph/reasoning chain for the request `I want to see classical art.` It displays the prepared navigation action but intentionally does not start robot navigation.

## File-based speech-to-text acceptance

Provide a real WAV file and expose `GROQ_API_KEY` in the shell environment:

```bash
PHASE8_SKIP_DOCKER_BUILD=1 \
./scripts/phase8_live_acceptance.sh /path/to/request.wav
```

The accepted test file format is PCM signed 16-bit, mono, 16 kHz WAV. The API key is never stored in this repository.

## Interactive development container

Start:

```bash
./start_museum_tiago.sh
```

Inside the container:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant museum_social_critic museum_video1_actors
source install/setup.bash
```

For detailed manual workflows, see `docs/user_manual.md`.
