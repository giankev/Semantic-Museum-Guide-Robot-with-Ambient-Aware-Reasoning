# Final demo terminal monitor

Run the monitor in a separate terminal attached to the existing
`museum_tiago` container, after the demo launch is running and before sending
the visitor request:

```bash
docker exec -it museum_tiago bash
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
source /root/exchange/exchange/museum_ws/install/setup.bash
python3 /root/exchange/scripts/demo_monitor.py
```

Add `--show-graph` to include the compact active-session scene graph:

```bash
python3 /root/exchange/scripts/demo_monitor.py --show-graph
```

The monitor is read-only: it only subscribes to the existing demo topics.
Unavailable topics remain blank (`—`). Press `Ctrl-C` to exit and restore the
terminal cursor.

## Sketch 1: one-command social-navigation demo

From the repository root on the host, start the complete Sketch 1 setup with:

```bash
./scripts/start_video1_demo.sh
```

The starter opens the supplied museum and anisotropic Nav2 launch, a six-person
deterministic crowd concentrated around the short video route, the terminal
monitor, and a video-control prompt. The prompt appears only after all six
people are moving and an additional five simulated seconds of warm-up. It also
shows the Nav2 ownership, 0.20 m/s speed limit, human-only Gazebo state-setting
allow-list, and measured Gazebo real-time factor. Start recording, then press
`Enter` in the control terminal to send the known-free central-hall goal
`(4.0, 8.0, 1.57)` through the normal Nav2 action.

Stop only the recorded Video 1 helper processes with:

```bash
./scripts/stop_video1_demo.sh
```
