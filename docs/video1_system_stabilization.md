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

## Running the diagnostic capture

```
./scripts/start_video1_animated_demo.sh --baseline --headless --runtime-audit --observe-only
```

Use the desktop's `DISPLAY`. Omit `--observe-only` only for an actual
single-goal comparison. `VIDEO1_SOFTWARE_RENDERING=1` is an explicit renderer
experiment, not an accepted performance configuration.
