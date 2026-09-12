# Eight-Actor social-navigation demo — validation in progress

Branch: `codex/video1-system-stabilization`. The final launcher defaults to eight
Actors; the 3/6/8 runtime stages are not yet accepted. The previous one-Actor
and no-people runs succeeded with one goal and no recoveries/controller aborts.
Historical benchmark files are unchanged.

```bash
./scripts/start_video1_final_animated_demo.sh
```

Internal stages: `--actors 3`, `--actors 6`, `--actors 8`; `--headless` is available
for navigation measurements, and `--runtime-audit` adds detailed geometry logs.
The existing `start_video1_animated_demo.sh` remains the one-Actor diagnostic
entry point, without the social filter unless explicitly enabled by the final
wrapper. Both retain Gazebo after recording and save every run separately.

## Actor geometry

Every Actor follows `x=cx+rx*cos(omega*t+phase)`,
`y=cy+ry*sin(omega*t+phase)`. Heading and velocity come from the analytic
trajectory derivative; the published pose is read back from the actual Actor.
Animation time follows distance traveled using the shipped walk.dae gait.
Each plugin is restricted to its Actor name; none controls TIAGo.

| Actor | Role | Center (m) | Radii (m) | omega (rad/s) |
|---|---|---|---|---|
| walker_1 | Parallel, accepted original | (1.8, 8.7) | (0.45, 1.3) | 0.28 |
| walker_2 | Peripheral west | (-5, 5) | (0.7, 1) | 0.22 |
| walker_3 | Crossing | (0, 6) | (1.8, 0.65) | 0.20 |
| walker_4 | Parallel west | (-3.1, 7) | (0.45, 1.5) | 0.28 |
| walker_5 | Peripheral east | (5, 5) | (0.7, 1) | 0.22 |
| walker_6 | Lateral north | (3.5, 14) | (1.2, 0.6) | 0.22 |
| walker_7 | North patrol | (-4.5, 15.5) | (0.7, 1.2) | 0.22 |
| walker_8 | East patrol | (5, 8) | (0.7, 1) | 0.20 |

Phases are fixed in `config/eight_actors.json`. The crossing phase initially
places walker_3 on the centerline at simulation time 135 s. No robot waypoint
or path is prescribed. Proxy-wall clearance is tested throughout every ellipse.

## Data and command paths

Individual physics-stamped `/museum/video1/actor_samples` are combined only
when all configured IDs have the **same timestamp**. One bridge publishes the
complete world-frame `/museum/video1/actor_states` and aligned odom-frame
`/people`, at 20 Hz. Incomplete frames are withheld; no missing Actor is invented.

`/people` still feeds the corrected anisotropic ProxemicForce critic with the
accepted scale 32, comfort distance 1.0, sigma 0.4 and front/side/back scales
1.4/1.0/0.8. The existing LiDAR detects museum geometry. The controlled walk.dae
experiment found no Actor returns at its laser plane, so social yielding uses
`/people` rather than assuming Actor obstacle-layer detections. Blue rays stay
visible. NVIDIA GUI offload is independent of the software-rendered sensor.

DWB and recovery velocities go through `/cmd_vel_nav` → Nav2 velocity smoother
→ `/museum/nav_cmd_vel` → `social_yield` → `/cmd_vel` → TIAGo's twist mux.
A readiness gate checks the actual ROS endpoints and refuses the goal if any
publisher bypasses the filter. No action is cancelled or reissued to yield.
Exactly one NavigateToPose target remains `(0,16,1.5708)`.

## Social yielding

The filter uses robot-relative position and person velocity. It ignores people
behind TIAGo, predicts entry into a forward corridor over 2 seconds, and scales
both translation and rotation together to preserve commanded curvature.

Current configuration in `config/social_yield.yaml`:

- Forward corridor half-width: 0.65 m; slowing distance: 2.5 m.
- Stop distance along the corridor: 1.3 m, with entry predicted within 1.2 s.
- Release distance: 1.65 m; release half-width: 0.85 m.
- Clear-time hysteresis: 0.8 simulation seconds before leaving YIELDING.
- Input freshness bound: 0.4 simulation seconds; missing/invalid inputs output zero.

This is explicit social interaction behavior in simulation, not a certified
collision-safety system. Normal DWB/ProxemicForce avoidance remains active.
The terminal reports CLEAR/SLOW/YIELDING, nearest relevant person, stream rate,
Actor count and goal count. JSON observations retain input command, output
command and physical robot speed. The final acceptance check requires a measured
moving → slowed/stopped → resumed sequence and navigation SUCCESS.

## Current validation status

Seven test groups pass, covering the original Humble failures, delayed action
acknowledgements, Actor motion, complete-frame aggregation, frame/velocity
rotation, forward crossing relevance, hysteresis, stale inputs and invalid
commands. A first startup exposed a missing executable permission. The next
pre-goal check exposed recovery publishers bypassing the filter; both were
corrected and their negative runs retained. Progressive navigation and visible
walking validation are still in progress; no final video success is claimed.

The first three-Actor crossing at phase 120 s produced a measured slowdown
but cleared about 2 m ahead of TIAGo, so a stop was correctly unnecessary.
The crossing phase was shifted to 135 s for a closer controlled interaction;
the robot goal and navigation configuration were not changed.

Three-Actor run `20260912T154035Z_actor` completed SUCCESS with one goal,
zero recoveries, zero invalid-trajectory/controller-abort/acknowledgement
failures, minimum center distance 1.009 m and RTF 0.499. It demonstrated
slowdown but no required stop; therefore its social stop/resume acceptance
check correctly failed. Independent subscribers measured every Actor and
aggregated /people at 20 Hz, with a maximum 0.05 s gap. Recorder batching and
a larger bounded best-effort queue address its lower observed sample rate.

Run `20260912T154908Z_actor` was cancelled at 61.27 s by the recorder's LiDAR
freshness gate. The sensor was still publishing: the audit subscription had a
60.696 s scan while the main subscription remained at 60.243 s. Humble's
convenience `rclpy.spin_once(node)` adds/removes the node on each call. A persistent
SingleThreadedExecutor now owns the recorder, with bounded callback batches and
unchanged sensor freshness limits. A real DDS test exercises busy and later
subscriptions and verifies persistent executor membership; all 25 recorder
tests pass. Runtime confirmation of this scheduling correction follows.

Runs `20260912T155716Z_actor` and `20260912T204626Z_actor` exposed recorder
service starvation after navigation started. The latter distinguished delayed
GetState RPCs from a reported inactive node, but its 15 s monitoring deadline
correctly stopped the experiment. Installed Humble executor inspection found
that alternating spin timeouts resets the ready-callback iterator. The recorder
now uses the same 5 ms timeout throughout each bounded eight-callback batch.
The DDS fairness regression now exercises 20 busy subscriptions, exceeding one
batch; all 26 recorder tests pass. Startup still requires fresh ACTIVE replies;
an observed inactive state fails immediately and missing monitoring remains
bounded. These negative runs are retained and do not validate the final scene.
