# Video 1 animated humans: audit and one-actor POC

**Status: DRAFT / NOT RUNTIME VALIDATED. This is not an accepted final video setup.**

Audited base: `integrate-supplied-reasoning-escort`, commit
`39e241033ca22b8294d171163e7b6fda52c9ec94` (2026-09-10, `video setting`).
The development environment had no `docker`, `ros2`, `gazebo`, `/opt/ros`,
or `/dev/dri`. The launcher was attempted and stopped at the missing-Docker
preflight. No navigation result, rendering result, actor animation, LiDAR
behavior, or performance measurement has been invented.

The requested order requires a successful one-actor runtime/visual test before
building a crowd. Accordingly **only one actor is implemented**. The 3, 6 and
8–10 actor stages and the final recording scene remain blocked on that test.
There is no crowd option or automatic promotion based on synthetic tests.

## A. Technical diagnosis

- The supplied navigation launch uses the accepted proxy collision world and
  known map, AMCL, NavFn, DWB and `museum_social_critic::ProxemicForceCritic`.
  `/museum/ground_truth_odom` supplies aligned simulation odometry and the sole
  `odom -> base_footprint` TF. AMCL supplies `map -> odom`. This is still AMCL
  navigation, but its odometry input is the project's existing ground truth
  adapter, not raw wheel odometry.
- The reasoning launch adds reasoning, semantic route dispatch, sessions and
  optional speech/language/engagement/scripted visitor. Video 1 only needs
  navigation. The isolated launch does not start other goal-producing nodes.
- Current `start_video1_demo.sh` defaults to **nine static humans plus a moving
  guide**. The ten-person static fallback requires `--static-guide`. It also
  requires an already running `museum_tiago` container, despite older wording
  suggesting that it creates the complete container itself.
- `demo_static_people.py` calls `SetEntityState` every 0.25 simulation seconds.
  It translates an unanimated standing mesh. Its triangle-wave guide reverses
  velocity and yaw instantaneously. The 0.12 m/s command is not evidence of
  uninterrupted 0.12 m/s published velocity.
- `museum_nav.world` sets `gazebo_ros_state.update_rate=1.0`. The people node
  differentiates these unstamped `ModelStates` using its receive-time ROS
  clock, rather than a simulation acquisition timestamp. The critic timeout
  is also **1.0 s**: there is no timing margin. Jitter may produce stale
  snapshots or inaccurate velocity. Even perfect 1 Hz sampling of the current
  triangle wave, from t=0 to 600 s, produces mean/min/max **0.1136 / 0.04 /
  0.12 m/s**, with **92%** of intervals above 0.10 m/s. This is a numerical
  reproduction from the current code, **not measured Gazebo data**.
- The older `start_video1_static_headless.sh` waits for six people while the
  current placement helper creates ten. It can time out for this reason.
  That older script is not used by this addition.
- The accepted parameters in the request exactly match the checked-in
  anisotropic YAML. No critic tuning or algorithm change is justified.
- Existing RViz `/plan`, `/local_plan` and footprint topic names agree with
  unnamespaced Humble Nav2 source. DWB publishes `/local_plan` when it has a
  subscriber; the new recorder provides one and counts actual messages.
  Runtime topic availability still needs testing. The late-starting RobotModel
  display used volatile durability for `/robot_description`; the disposable
  RViz copy requests transient local durability.
- Existing social zones are shifted ellipses. They approximate, but do not
  exactly represent, the critic's two longitudinal scales. The new visualizer
  draws the two half-ellipses at effective distance = comfort distance and
  expires markers after one simulation second. The contour is a comfort
  visualization, not a hard collision boundary.
- The old monitor subtracts odom robot positions from people labeled `map`
  without a TF transformation and does not expire old data. The new recorder
  performs frame-aware, timestamp-bounded comparisons.
- The current start script attempts GPU forwarding, so software rendering
  cannot be diagnosed from the repository alone. The isolated
  launcher now follows the stable launcher's NVIDIA/DRI selection. This is a
  launch configuration, not proof that OpenGL selected the GPU.
- Nothing in the audited visualization code proves the reported cylinder at
  the mouse cursor was caused by it. The new camera comes from world SDF and
  performs no mouse, model-insertion, or robot relocation commands.

ROS distribution: **Humble**. Gazebo family: **Classic 11**, checked before
launch. Exact installed Gazebo/Nav2 versions and image digest are unknown in
this environment; the Dockerfile does not pin their apt versions. Every run
captures them in `versions.txt` and `container.txt` rather than guessing.

## B. Selected actor architecture

`<actor>` with Gazebo's `walk.dae` skin and walking skeleton. A small C++
ModelPlugin is necessary for direct actor animation/pose access. It refuses
to attach to any model except `video1_walker_1`, dynamically cast as an Actor.
It updates that actor's world pose on simulation updates, advances skeleton
time by distance traveled, and publishes its read-back pose with the analytic
velocity of the same applied path at 20 Hz of simulation time.

`SetWorldPose` here applies **only to the human actor**. TIAGo is never moved
through Gazebo. The robot receives one ordinary `NavigateToPose` request.
The gait rate is calculated from the loaded skeleton's duration and root
translation. Limb animation and foot contact must still be visually checked.

Gazebo Classic supports COLLADA/BVH actors. They do not behave as dynamic
collision bodies; their rendered geometry can be seen by GPU sensors.
Sources: [official actor tutorial](https://classic.gazebosim.org/tutorials?tut=actor),
[Gazebo 11 actor plugin](https://github.com/gazebosim/gazebo-classic/blob/b22c6e15e52299865b31093b8feebc9ca19e26e8/plugins/ActorPlugin.cc).

Actors are inserted into the world's model collection by `World::LoadActor`.
The ROS state plugin enumerates that collection, so their presence in
`/gazebo/model_states` is expected from source. That does not make its
static-model twist a dependable walking velocity. The new state stream is
independent of that 1 Hz publisher. References:
[World::LoadActor](https://github.com/gazebosim/gazebo-classic/blob/b22c6e15e52299865b31093b8feebc9ca19e26e8/gazebo/physics/World.cc),
[gazebo_ros_state](https://github.com/ros-simulation/gazebo_ros_pkgs/blob/ros2/gazebo_ros/src/gazebo_ros_state.cpp),
[Humble DWB publisher](https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/dwb_core/src/publisher.cpp).

## C. Exact source changes

New files:

- `scripts/start_video1_animated_demo.sh`
- `scripts/stop_video1_animated_demo.sh`
- `scripts/prepare_video1_animated_world.py`
- `docs/video1_animated_demo.md`
- `exchange/museum_ws/src/museum_video1_actors/package.xml`
- `exchange/museum_ws/src/museum_video1_actors/CMakeLists.txt`
- `exchange/museum_ws/src/museum_video1_actors/include/museum_video1_actors/motion.hpp`
- `exchange/museum_ws/src/museum_video1_actors/src/actor_plugin.cpp`
- `exchange/museum_ws/src/museum_video1_actors/config/one_actor.json`
- `exchange/museum_ws/src/museum_video1_actors/launch/video1.launch.py`
- `exchange/museum_ws/src/museum_video1_actors/scripts/people_bridge.py`
- `exchange/museum_ws/src/museum_video1_actors/scripts/demo_math.py`
- `exchange/museum_ws/src/museum_video1_actors/scripts/record_demo.py`
- `exchange/museum_ws/src/museum_video1_actors/scripts/social_markers.py`
- `exchange/museum_ws/src/museum_video1_actors/test/test_actor_motion.cpp`
- `exchange/museum_ws/src/museum_video1_actors/test/test_demo_tools.py`

Modified files, under `museum_assistant/launch/`:

- `tiago_supplied_museum_nav_world.launch.py`: optional `world_file` argument.
- `tiago_supplied_museum_ground_truth_odom.launch.py`: forward that argument.

Both defaults remain the original world. Existing demo scripts, critic source,
Nav2 YAMLs, map/world assets, benchmark scripts and benchmark results are
unchanged. Generated world/RViz copies and all run evidence live under the
already ignored `log/video1_animated/<UTC-time>_<mode>/` directory.

## D. Asset and license

Use the **already installed Gazebo 11 `media/models/walk.dae`**, normally
`/usr/share/gazebo-11/media/models/walk.dae` inside the existing image.
No Fuel account, animated-human package, model dependency, texture download,
or host ROS installation is added. The asset has 31 skeleton animation
channels, no external texture references, and is 2,277,322 bytes.

- Exact upstream revision: `b22c6e15e52299865b31093b8feebc9ca19e26e8`.
- [Exact asset](https://github.com/gazebosim/gazebo-classic/blob/b22c6e15e52299865b31093b8feebc9ca19e26e8/media/models/walk.dae).
- Upstream declared license: [Apache 2.0](https://github.com/gazebosim/gazebo-classic/blob/b22c6e15e52299865b31093b8feebc9ca19e26e8/LICENSE).
- Asset metadata author: `Blender User`; do not invent a specific creator.
- SHA-256: `49af0df3a319d1cb8ca2cebf02dbd00f625e5d5bec820bc5e109925b18b65c6e`.

The generator checks the exact hash. If the asset is absent or differs, it
stops and records the reason in `preparation.log`. Repair the asset in the
Docker image using the pinned upstream source and verify the hash before
retrying; do not substitute a standing mesh or remove the check. No model is
vendored or redistributed by this PR. A reference copy was inspected outside
the repository for the offline asset/world checks.

## E. Human path and current count

**One experimental walker; zero accepted final animated crowd scenes.**

`one_actor.json` defines, in world coordinates:

```
x(t) = 1.8 + 0.45 cos(0.28 t)
y(t) = 8.7 + 1.30 sin(0.28 t)
vx(t) = -0.126 sin(0.28 t)
vy(t) =  0.364 cos(0.28 t)
theta(t) = atan2(vy, vx)
```

The loop period is approximately 22.44 simulation seconds. Its lane is
x=1.35..2.25, y=7.4..10.0, lateral to the nominal robot route and within the
north opening. There are no random phases, sharp triangle-wave turns or
teleports at loop closure. The path has no dependency on robot goals or poses.
Numerical testing clears all proxy wall boxes with a 0.35 m human disk.
This does not prove mesh-level clearance or avoidance of a moving robot.

Analytic speed over 10,001 samples: min **0.126**, mean **0.259687**, max
**0.364 m/s**; **100%** above 0.10 m/s. These are mathematical checks, not
Gazebo or `/people` measurements. The run also measures the real stream and
an independent `GetEntityState` observation of the actor.

## F. `/people` integration

```
Gazebo actor plugin -> /museum/video1/actor_states (world, 20 Hz)
same-stamp raw + aligned robot odometry -> measured world-to-odom transform
people_bridge.py -> /people (social_nav_msgs/msg/Pedestrians, odom)
/people -> unchanged DWB ProxemicForceCritic and read-only visualization
```

The bridge pairs `/ground_truth_odom` and `/museum/ground_truth_odom` by their
exact source timestamp. It transforms position, heading and velocity into
odom, preserving the actor's acquisition timestamp. It does not label world
coordinates as map coordinates, differentiate delayed 1 Hz messages, or
publish predicted people after an actor disappears. Only one publisher on
`/people` is allowed by the actor readiness gate.

Startup checks all nine Nav2/localization lifecycle nodes, every accepted
critic parameter, live odometry, one actor, sustained heading speed and
agreement with Gazebo's actor pose service. Goal submission is scheduled at
simulation time 60 s. If startup misses the schedule it fails before sending
a goal; a larger explicit `--goal-time` must be recorded consistently across
comparison runs. A simulation-clock reset requires a fresh run.

## G. LiDAR and local obstacle layer

**Neither `/scan_raw` nor the obstacle/inflation layers are changed.**
There is no filtering of actor returns and no globally disabled laser.
Actor visibility in the GPU scan is expected but **not runtime confirmed**.

The recorder transforms scan endpoints and actor observations at matching
simulation times, counts endpoints within 0.40 m of the person, and checks
nearby lethal local-costmap cells while the person is inside its window.
It separately observes DWB candidate scores for `ProxemicForce`. These are
spatial associations, not definitive attribution: walls can cause nearby
returns too. Inspect the single actor when the robot approaches its lane,
compare with the no-human baseline, and examine the scan/costmap in RViz.
No returns while the actor is outside the local window are inconclusive.

If both appear, the hard geometric obstacle cost and soft proxemic cost are
both active. That is not by itself a bug or reason to hide obstacles.
If this one-actor test demonstrates blocking, retain the logs and resolve
the specific geometry/timing issue before considering a VIDEO-only change.
No runtime blocker has been proved here and no alternative mechanism chosen.

## H–I. Verification and evidence

Completed in the development environment:

- Eight Python unittest checks: PASS (frame/velocity transforms, timestamp and
  speed statistics, source-world preservation, lane geometry, one goal call).
- Standalone C++ trajectory test compiled with `-Wall -Wextra -Werror`: PASS,
  including numerical derivatives, loop continuity and 10,001 speed samples.
- Python compilation and Bash syntax: PASS.
- Generated one-actor world with the pinned real COLLADA asset: PASS as XML;
  this is not Gazebo loading/rendering validation.
- Missing-Docker launcher preflight: correctly failed before any ROS goal.
- `git diff --check`: PASS.

Not performed: C++ Gazebo-plugin compilation/link/loading in Docker, baseline
navigation, static fallback navigation, one-actor navigation, walking visual
inspection, LiDAR attribution, GUI coexistence, GPU renderer/FPS, final crowd.
The complete existing ROS test suite was not executable here either.

Each runtime attempt produces:

| File | Evidence |
| --- | --- |
| `build.log`, `tests.log` | Container build and isolated tests |
| `versions.txt`, `container.txt`, `graphics.txt` | Gazebo/ROS interfaces, installed package versions, image/device details, renderer if `glxinfo` is available |
| `git_head.txt`, `git_status.txt`, `museum.manifest.json` | Source revision, working changes, original/generated world and asset hashes |
| `runtime.log` | Gazebo, Nav2, bridge and RViz output |
| `observations.jsonl` | Timestamped people, robot pose/velocity, actor service observations, warning/error logs and scan/costmap associations |
| `summary.json` | Nav2 result, map/world/odom final pose, min center/disk clearance, recoveries, invalid-trajectory/progress messages, angular reversals/spin time, actual speed statistics, frequency, RTF and evidence counts |
| `gazebo_stats.csv`, `docker_stats.jsonl` | Gazebo server statistics and Docker CPU/memory samples |

The recorder reports both people simulation Hz and wall Hz. It measures RTF
from advancing simulation time versus monotonic wall time; this is not GUI
FPS. Gazebo GUI FPS stays explicitly `NOT_MEASURED`; observe its GUI indicator
if available. Do not call `gz stats` iterations rendering FPS. Forwarding a
GPU does not prove Gazebo or RViz are using it; consult the actual renderer.

Automated checks require one successful goal, final position within 0.5 m,
no reported recoveries/progress/trajectory failures, paths, no long stationary
spin, sufficient clearance and, for the actor, observed scoring, fresh motion
and scan/costmap evidence. Angular reversal detection uses a 0.08 rad/s
deadband and 0.5 s persistence; the POC flags more than six reversals or a
continuous stationary spin over eight simulation seconds. These are demo
checks, not changes to the benchmark protocol. Human clearance is measured
between planar centers; the disk estimate subtracts 0.28+0.35 m and is not a
Gazebo contact measurement.

The launcher returns nonzero when automated checks fail and retains evidence.
After runtime starts it leaves its container and GUIs open for inspection. `--observe-only` never sends a navigation goal.
Even a successful automatic run sets `final_scene_accepted=false`: visual
walking, absence of mesh intersections, LiDAR attribution and recording
quality require inspection. A curved path alone does not prove that the
social critic caused the deviation; obstacle costs can also contribute.

## J. Commands on the simulation computer

From this branch's repository root, with the existing image available:

```bash
./scripts/start_video1_animated_demo.sh --baseline --headless
./scripts/stop_video1_animated_demo.sh
./scripts/start_video1_animated_demo.sh --static --headless
./scripts/stop_video1_animated_demo.sh
./scripts/start_video1_animated_demo.sh --observe-only
./scripts/stop_video1_animated_demo.sh
./scripts/start_video1_animated_demo.sh
```

The first two commands run the no-human and current static-placement controls
through the new instrumented launch. They do not replace the original static
launcher. The observation run permits inspecting one actor's actual limb
animation before navigation. The final command runs the one-actor navigation
test with Gazebo, RViz and the console control/monitor. It is a **POC recording
command, not the requested final multi-human recording command**.

The launcher creates `museum_video1_animated_<uid>` on isolated ROS domain
107 and builds needed packages sequentially. The existing `museum_tiago`
container is neither reused nor stopped. To choose another unused domain:

```bash
VIDEO1_ROS_DOMAIN_ID=108 ./scripts/start_video1_animated_demo.sh
```

Gazebo starts with its bird's-eye camera; RViz requests a window to its right.
Final window positioning depends on the desktop/window manager. The terminal
running the command is the social control/monitor. If desktop authentication
fails, inspect `runtime.log` and the host `DISPLAY`/`XAUTHORITY`; the script
uses the stable launcher's local Docker X access rule, recorded in `xhost.txt`.
Use `--headless` for navigation
measurements, then repeat the same accepted scenario with both GUIs for
recording/performance checks.

Stop the experiment and keep every log:

```bash
./scripts/stop_video1_animated_demo.sh
```

The existing validated fallback remains:

```bash
# With the original museum_tiago container already running:
./scripts/start_video1_demo.sh --static-guide
```

After the one-actor runtime and visual evidence pass, implement and validate
three actors, then six, then evaluate whether 8–10 are practical. Do not
describe any of those unimplemented stages as tested or ready to record.

## Infrastructure repair after the real-machine startup crashes

The reported build and original two tests passed on the real machine, but the
recorder stopped at simulation time zero, before readiness and before sending
any goal. Those summaries are **not evidence of navigation/Actor failures**.
One-Actor runtime and visual acceptance are still pending.

The launcher now probes Gazebo using `pkg-config --modversion gazebo` and
checks its exit status as well as requiring version 11. It never uses the
Gazebo executables' unreliable `--version` exit status. Recorder construction
uses `lifecycle_clients`, avoiding the inherited read-only `Node.services`.
Log severity uses numeric `rclpy.logging.LoggingSeverity.WARN`, with explicit
single-byte conversion for generated message levels. It does not compare
against the generated `Log.WARN` constant.

Audit outcomes:

- All recorder subscriptions have guarded callbacks. Optional log, scan,
  costmap, world-pose, path, score and feedback errors get named diagnostics,
  error counts and last-error text. They cannot terminate the experiment.
  Invalid critical people/odometry/action-status inputs still fail clearly.
  Missing optional evidence cannot produce an automated pass.
- Lifecycle responses must be fresh and ACTIVE for all nine configured nodes.
  Service futures handle exceptions, release pending requests and retry;
  requests time out after five wall seconds. Parameter responses must contain
  the complete accepted parameter set. No accepted parameters were changed.
- Action readiness is checked before sending the single goal. Rejection,
  result exceptions, timeout and cancellation acknowledgement are explicit.
  There is no retry of goal submission and no new robot waypoint.
- The recorder defaults to and requires simulation time. Zero clock cannot
  pass readiness; pre-clock odometry is ignored. Backward time is detected
  before odometry throttling, and a stalled clock has a wall-time deadline.
- Data subscriptions use best-effort/volatile QoS, compatible with reliable
  and sensor-data publishers. Action status keeps transient-local durability.
  The Actor bridge can start before Gazebo: it waits for paired odometry and
  a live actor stream. Pose polling waits for that stream and the service;
  pose agreement must be recent before readiness.
- Gazebo Classic's ROS2 `GetEntityState` response has `header.stamp`,
  `state.pose`, and `success`; unsuccessful responses are never used as poses.
  See the [upstream service definition](https://github.com/ros-simulation/gazebo_ros_pkgs/blob/ros2/gazebo_msgs/srv/GetEntityState.srv).
- `/plan`, `/local_plan` and `/evaluation` are the expected unnamespaced Nav2
  topics. DWB evaluation publication is conditional; absence is inconclusive,
  and never gates goal submission. Topic names/types and per-topic message
  counts are captured to expose differing runtime installations. See the
  [Humble DWB publisher](https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/dwb_core/src/publisher.cpp).
- RViz may start before its data publishers. Its disposable RobotModel config
  requests transient-local robot description, and TF/map displays can recover
  as publishers appear. GUI visibility still requires real-machine evidence;
  no additional arbitrary startup sleep was added.
- Empty people/path/evaluation streams cannot be mistaken for positive
  evidence. Invalid costmap dimensions/resolution and nonfinite pose values
  are diagnosed. Optional distance calculations cannot terminate odometry
  handling. Final map conversion uses the observed odometry frame.
- Preparation failures still stop the owned container. After runtime launch,
  recorder failure or incomplete evidence leaves Gazebo/RViz running and
  preserves the nonzero exit status. An interactive terminal waits for Enter
  before returning to the shell; the explicit stop script closes the scene.

`summary.json` now includes `experiment_phase`, `readiness_reached`, named
`diagnostics`, and `topic_inventory`. Checks that were never exercised are
`null` (NOT_MEASURED / INCONCLUSIVE), not false runtime results. A pre-goal
crash marks all experiment checks unmeasured. Navigation outcome and evidence
completeness are separate; visual walking is always a manual check.

Focused regressions run as the additional `video1_recorder_runtime` CTest in
the launcher's existing container build/test step. They construct a real Humble
Node and use actual generated messages, including a simulated byte-constant
regression. They also cover optional callback faults, critical input faults,
service exceptions/timeouts, Gazebo response layout, zero/reset clock, QoS,
action exceptions/single submission and pre-navigation summaries. No robotics
packages are installed on the host.

Repair verification completed in `museum-tiago:humble` (image ID prefix
`be46ae0e5c16`) with networking disabled and repository mounted read-only:
three-package sequential build PASS; CTest **3/3 PASS, zero errors/failures/
skips**, including 15 recorder/launcher regressions and the original eight
Python checks plus C++ motion test. The shell regression executes the launcher
with a Docker stub and checks that preparation failure stops its container,
whereas recorder failure preserves it and returns the failure exit code.
Python syntax, Bash syntax and `git diff --check` passed. This verifies build
and infrastructure/API behavior, not a live Gazebo Actor/navigation/GUI run.

## DDS startup repair after d992839

The complete `20260910T213035Z_actor/runtime.log` (765 lines) and its graphics
and container evidence were reviewed. `ROS_LOCALHOST_ONLY=1` forced CycloneDDS
onto `lo`. Cyclone reported that this interface was not multicast-capable and
fell back to automatic participant indexes. The installed versions are
CycloneDDS `0.10.5-2jammy.20260226.013234` and rmw_cyclonedds_cpp
`1.3.4-1jammy.20260605.121029`. In Cyclone 0.10.5 the default
`MaxAutoParticipantIndex` is **9**, not a limit on the number of ROS node names.
Exhaustion of the candidate unicast ports prevented new processes from
creating DDS participants. The log shows `gzserver` itself aborting with
`RCLError`/exit -6 at 21:30:54, before Nav2 startup. TIAGo's spawn process also
failed to create a participant. The controller-manager, map and TF failures
therefore do not establish separate controller or map defects.

Sources: [Humble localhost interface selection](https://github.com/ros2/rmw_cyclonedds/blob/humble/rmw_cyclonedds_cpp/src/rmw_node.cpp),
[Cyclone 0.10.5 fallback and socket allocation](https://github.com/eclipse-cyclonedds/cyclonedds/blob/0.10.5/src/core/ddsi/src/q_init.c),
[0.10.5 default index limit](https://github.com/eclipse-cyclonedds/cyclonedds/blob/0.10.5/src/core/ddsi/include/dds/ddsi/ddsi_cfgelems.h).

The POC launcher retains host networking, CycloneDDS, and dedicated domain
107, but removes the localhost override. The existing image defaults to
`ROS_LOCALHOST_ONLY=0`; host shell variables are not implicitly forwarded by
Docker. This matches the validated `start_museum_tiago.sh` interface behavior.
There is no production Cyclone XML, participant ceiling change, controller
redesign or Nav2 change. An available host interface with working multicast is
still a runtime prerequisite. `dds_environment.txt` records effective DDS
variables, versions and interface flags so an offline/non-multicast host does
not silently get described as validated.

After all existing readiness checks succeed, the recorder starts
`probe_dds.py` as a **new OS process**, with its own rclpy context and DDS
participant. While the stack and recorder remain alive, it must receive an
advancing `/clock`, a nonempty transient-local `/map`, the one `walker_1` on
`/people`, and a response from `/controller_manager/list_controllers`. The
recorder keeps spinning during this check and rechecks readiness afterwards.
Only then may the original single scheduled goal be sent. `dds_probe.json`
and `dds_probe.log` retain PID, admission/communication results and stderr;
`summary.json` includes `dds_admission`. A process timeout, admission error or
missing endpoint is not a pass. The recorder also detects the explicit
participant-exhaustion error in `runtime.log` before readiness, rather than
waiting for a generic timeout. These checks do not count ROS node names.

### Gazebo GUI diagnosis and evidence

**The precise gzclient exit-255 cause remains runtime-unknown.** Its exit
occurs after the DDS-driven server abort, so loss of the server/master is a
plausible explanation, not proof of a rendering defect. No gzclient stderr,
Ogre exception or X authorization error precedes the exit in the supplied
log. RViz initialized OpenGL 4.6; that demonstrates usable X/GL for RViz but
does not establish Gazebo's renderer. `graphics.txt` says glxinfo is absent,
so the GPU/vendor/renderer was not measured.

`container.txt` shows the DRI path was selected, not NVIDIA device requests.
The DRI nodes are present with root ownership and read/write access for the
container's root user. Both launchers already used `--device=/dev/dri:/dev/dri`
and `LIBGL_ALWAYS_SOFTWARE=0` (the false setting, not a request for software
rendering); there is no evidence to change that working baseline choice.
The POC now also matches the stable launcher's `xhost +local:docker`, DISPLAY
fallback `:0`, X11 socket mount, Qt setting and `--gpus all` selection. It no
longer imposes a separate Xauthority mount or extra NVIDIA capability setting.
No blanket `xhost +` or host package installation is introduced.

PAL's installed launch hardcodes plain `gzclient` and exposes no verbose flag.
The POC generates a per-run PATH wrapper that execs the installed gzclient
with `--verbose`. PAL still starts its original client in its scoped model/
plugin environment and original order. No second GUI is launched; the PAL
server/spawn/controller path is unchanged.
Gazebo's actual stderr now reaches `runtime.log`; `/root/.gazebo` and ROS launch
logs are persisted under the run's `gazebo/` and `ros/` directories. Inspect
Ogre's `GL_VENDOR`/`GL_RENDERER` if GL initialization occurs. `graphics.txt`
records effective DISPLAY/Xauthority/render settings, UID and device/socket
permissions; `xhost.txt` preserves the access-rule command outcome. Missing
renderer evidence stays explicitly NOT_MEASURED.

New regression coverage includes separate-process admission and real topic/
service communication, a deterministic exhausted-port rejection (test-only
XML), empty-graph rejection, no goal after a failed admission check, immediate
classification of DDS exhaustion in the log, and launcher checks retaining
host networking/domain isolation without reintroducing localhost or custom
Cyclone XML. Synthetic publishers in the DDS test are test fixtures only;
they are never launched by the demo.

Next real-machine run, from the repository root:

```bash
git fetch origin &&
git switch codex/video1-actor-poc &&
git pull --ff-only origin codex/video1-actor-poc &&
./scripts/stop_video1_animated_demo.sh &&
./scripts/start_video1_animated_demo.sh
```

Still required: real host DDS stability and CLI admission with the whole
stack, Gazebo GUI alive, TIAGo spawned, advancing clock, controller manager,
ACTIVE Nav2, map, one walking Actor, fresh people/velocity, exactly one goal
at `(0,16,1.5708)` and the navigation outcome. No live runtime acceptance or
crowd expansion follows from the container regression tests.

DDS repair verification: sequential build of all three required packages in
`museum-tiago:humble` PASS; CTest **4/4 PASS**, zero errors/failures/skips
(C++ motion, eight geometry/world checks, 18 recorder/launcher checks, three
DDS process/communication checks). Tests used a Docker bridge interface with
normal multicast selection, a read-only repository mount and disposable
build directories. After the final GUI wrapper adjustment, all 18 recorder/
launcher checks were rerun successfully. Bash/Python syntax and full diff
review passed. No Gazebo GUI, Actor runtime or navigation success is claimed.
