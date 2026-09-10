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

The starter opens Gazebo in a bird's-eye view, the dedicated Video 1 RViz view,
the social monitor, and the video-control prompt. It places ten visible NPCs:
nine remain static while only `guide_1` moves slowly along a bounded lateral
lane. The control prompt waits for active Nav2 and ten `/people` entries, then
sends exactly one normal `NavigateToPose` goal to north gallery
`(0.0, 16.0, 1.5708)`.

Use the validated all-static fallback without changing the navigation setup:

```bash
./scripts/start_video1_demo.sh --static-guide
```

The RViz view subscribes to `/map`, `/plan`, `/local_plan`, the local footprint,
and the read-only `/museum/social_markers` visualization. RViz readiness is
reported but never gates or commands navigation.

Stop only the recorded Video 1 helper processes with:

```bash
./scripts/stop_video1_demo.sh
```
