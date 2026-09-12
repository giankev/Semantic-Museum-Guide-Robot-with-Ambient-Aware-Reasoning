# Video 1 system stabilization (in progress)

Branch: `codex/video1-system-stabilization`, based on `4c1341b`.
No multi-Actor or final-video acceptance is claimed. Historical benchmark
outputs and accepted navigation parameters remain unchanged.

## Reproduced findings

* The controller gate matched `inactive` as `active`. Matching the complete
  state also requires stripping the ANSI colors emitted by this Humble CLI.
  Regression coverage uses both colored and plain active/inactive/unconfigured
  responses.
* Headless Gazebo still requires a rendering display for GPU LiDAR. The POC
  now forwards the desktop display with `--headless`, and reports a missing
  display before starting the container.
* The recorder previously allowed navigation with completely unusable scans.
  It now requires fresh finite returns from the enclosed museum and records
  sensor health independently of optional Actor association measurements.
  Sustained invalid scans fail explicitly before any goal is sent.
* A read-only audit records world/aligned/wheel odometry, map/odom/base TF,
  plans, local-costmap geometry and plan-point occupancy, and full scans at
  one snapshot per wall second. Navigation errors trigger additional bounded
  snapshots. This is observational correlation, not an atomic Nav2 internal
  snapshot. Older installed Humble rclpy lacks publisher GIDs in MessageInfo;
  unavailable transform authority is explicitly marked rather than inferred.

## Runtime evidence collected on this machine

Evidence remains under ignored `log/video1_system_audit/` and
`log/video1_animated/`; negative results are retained.

* `old_live_complete`: the original completed Actor simulation, still running
  ten hours later, emitted no finite scan returns. World and aligned odometry
  differed by only the captured initial rigid alignment; AMCL differed much
  more. This late observation cannot reconstruct the earlier DWB events.
* `20260911T083322Z_baseline`: first fresh stationary baseline reproduced
  unusable scans. A newly tightened gate initially failed on ANSI colors;
  the run was interrupted before navigation, and this diagnostic regression
  was corrected and tested.
* `20260911T083557Z_baseline`: corrected controller startup, ACTIVE Nav2,
  separate-process DDS probe passed, observation only. Intel UHD renderer.
* `lidar_positive_control_intel.json`: 666/666 **negative infinity** returns
  before, during and after spawning a known box 2 m ahead of stationary TIAGo.
  Expected front return approximately 1.598 m. The audit box was deleted.
* `sensor_types_intel.log`: independent stationary sensor rig, identical
  target: CPU `ray` returned 100/100 finite rays (minimum 1.800023 m); both
  `gpu_ray` and its `gpu_lidar` alias returned 100/100 negative infinity.
  The rig was deleted. This excludes Actor presence and TIAGo self-occlusion
  as necessary causes of that failure. Graphics/world isolation continues.

## Odometry source verification

TIAGo uses PAL `libgazebo_world_odometry.so`, not Gazebo's p3d plugin. The
[PAL source](https://github.com/pal-robotics/pal_gazebo_plugins/blob/humble-devel/src/gazebo_world_odometry.cpp)
uses `RelativeLinearVel` and `RelativeAngularVel`. Copying its twist to the
aligned odometry retains the child-frame velocity contract; rotating it as
though it were a world-frame velocity would introduce a bug. The 100 Hz raw
world pose is aligned once to the initial odometry origin. AMCL remains the
map-to-odom authority. No localization architecture change has been made yet.

## Renderer isolation and first clean navigation

The same positive-control rig under llvmpipe returned 100/100 finite values
for both GPU sensor types (minimum 1.800082 m), matching the CPU reference
(1.800023 m). The real TIAGo box test also recovered its expected front
return: approximately 1.57–1.60 m with noise and finite angular sampling.
The Intel rendering path's unusable GPU ranges are therefore a reproduced
root cause; Actor presence is not necessary for it. Blue ray visualization
and the GPU LiDAR sensor type remain enabled.

`VIDEO1_SERVER_RENDERER=software` applies llvmpipe only to gzserver. Gazebo
GUI and RViz keep the regular hardware renderer. Separate server/client
Ogre logs preserve the actual renderer. The all-software option remains
available as a controlled comparison.

No-people run `20260911T084717Z_baseline`, with working GPU LiDAR and the
unchanged accepted Nav2 YAML:

| Measurement | Result |
|---|---|
| Navigation | SUCCESS; exactly one goal |
| Navigation simulated duration | 141.715 s |
| Total recorder wall duration | 302.333 s |
| Final world pose | (0.01255, 15.92353, 1.91191) |
| Final map pose | (0.09692, 15.82968, 1.91302) |
| World goal position error | 0.0775 m |
| Map/world position difference | 0.1262 m |
| Recoveries / no-valid trajectories | 0 / 0 |
| RTF | 0.677 |

One clean baseline alone does not establish repeatability or Actor acceptance.
The global mesh and simplified collision map are not identical (a stationary
scan/map endpoint comparison confirms differences), but this baseline has
consistent localization and no DWB failures. No map change is justified by
this result alone.

One-Actor GUI run `20260912T091313Z_actor`, using the 200 ms BT timeout,
completed SUCCESS with exactly one goal. Navigation took 138.485 simulation
seconds / 293.616 wall seconds; RTF over the recorder run was 0.435.
Final world pose was (0.05136, 15.92735, 1.91505), map pose
(0.09894, 15.83355, 1.91578): world position error 0.089 m and map/world
difference 0.105 m. Recoveries, invalid-trajectory messages, controller
aborts, acknowledgement timeouts and angular reversals were all zero.
Minimum person center distance was 0.994 m. One startup lifecycle-service
timeout recovered; all critical streams remained usable. This run used
llvmpipe for both server and GUI. Its window was minimized during part of
the run, so the stale hidden-window capture is not animation evidence.
Repeated runs and the final graphics configuration are still pending.

Native TF attribution confirms one observed authority for each main edge:
AMCL for map→odom, simulation_ground_truth_odom for odom→base_footprint, and
robot_state_publisher for the robot links. mobile_base_controller advertises
a TF endpoint but did not publish that edge after its override. Endpoint
presence alone would have produced a false duplicate-TF diagnosis. This
Cyclone version exposes instance handles in native message metadata, while
its graph exposes GUIDs; the read-only Fast DDS probe provides matching wire
GUIDs. See `tf_authorities_guid.jsonl`.

## ProxemicForce corrections

Math tests reproduce three ingestion/prediction defects: a permitted zero
heading threshold divided stationary velocity by zero; future/nonfinite
states were not rejected; prediction started at the old message pose rather
than advancing it to the control-cycle time. Corrections retain the logistic
cost, anisotropic geometry, MAX aggregation, ignored identifiers and every
accepted parameter. Static people are unchanged by age projection. These
defects are not claimed to have caused the historical PathDist/GoalDist errors.

## Running the diagnostic capture

### Controlled Actor / LiDAR result

`actor_lidar_fresh_plugin.json` completed with the freshly loaded plugin and
no control errors. TIAGo stayed stationary. The known box changed the front
return from 6.67 m to 1.57–1.60 m and populated the local obstacle layer.
After deleting the box, a frozen Actor at (2.000, -0.001) was observed for
6.41 simulation seconds, then a walking Actor crossed the front beams for
51.77 simulation seconds (more than four complete circular laps).

Across 64 frozen and 516 moving scan samples, **zero** returns were within
0.5 m of the Actor's expected range. Moving range was 1.10–2.50 m and bearing
covered -0.400 to +0.400 rad. Matched-beam changes against the no-Actor median
were 0.0069 m median / 0.0492 m maximum, consistent with the configured scan
noise rather than a human-sized foreground return. Full scans are retained.

The frozen Actor's vicinity contained two lethal cells, but they were the
*same two box cells already present after box deletion*, persisting even
after both Actors were removed. Attributing those cells to the Actor would
be false. This is a ray-clearing gap in the stationary synthetic deletion
control, not evidence of Actor obstacle marking.

Conclusion for this exact walk.dae/plugin/GPU-LiDAR configuration: the Actor
produces no detectable returns in the robot's 0.195 m laser plane.
Social avoidance comes from /people and ProxemicForce, while LiDAR remains
enabled for the museum geometry. This does not generalize to ordinary human
models, other Actor assets, or other sensor heights. Positive laser/costmap
association is consequently an observation, not an Actor acceptance gate.

GUI run `20260911T171333Z_actor` recovered finite scans with software rendering
only on gzserver, but reproduced ComputePathToPose / FollowPath acknowledgement
timeouts and controller aborts. The first timeout sequence occurred with zero
ProxemicForce cost and without a PathDist rejection. It was explicitly cancelled;
this is retained negative evidence, not a successful Actor validation.

The accepted BT acknowledgement deadline is 20 ms. A real Humble BtActionNode
test with a server delaying acknowledgement 75 ms reproduces failure at 20 ms
and success at 200 ms, three paired repetitions. The launcher now writes a
per-run Nav2 YAML with only default_server_timeout changed to 200 ms, records
source/effective hashes and the changed field, and checks the live parameter
before sending a goal. `--accepted-nav2` retains the 20 ms counterfactual.
Controller/critic parameters and historical benchmark inputs stay intact.
Full-navigation comparisons at 200 ms remain necessary.

The recorder's dynamic TF subscription now uses a depth-five sensor queue;
the depth-100 default could leave its *observations* behind the robot under
GUI load. Static TF retains transient-local durability. This does not alter
the robot's TF publishers or Nav2 subscriptions. Comparisons must still use
matched timestamps before attributing an apparent pose difference to AMCL.

Package-level sequential builds did not bound compiler jobs: the installed
colcon still passed `-j8`. Explicit `MAKEFLAGS='-j1 -l1'` bounds compilation
on the 8 GB machine, independently of the package executor.

```
./scripts/start_video1_animated_demo.sh --baseline --headless --runtime-audit --observe-only
```

Use the desktop's `DISPLAY`. Omit `--observe-only` only for an actual
single-goal comparison. `VIDEO1_SOFTWARE_RENDERING=1` is an explicit renderer
experiment, not an accepted performance configuration.
