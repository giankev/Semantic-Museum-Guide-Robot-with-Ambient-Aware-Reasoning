# Phase 6 Minimal Human-Aware Navigation Variant

## Status

Phase 6 is runtime-validated through the opt-in custom trajectory critic added
in Phase 6B. The earlier generic SocialLayer integration still has technical
value but failed its behavioral comparison, and the bounded Phase 6A generic
DWB tuning remains rejected. The accepted variant scores DWB trajectories
directly from `/people` and produced a repeatable, measurable increase in
clearance without changing the baseline stack.

The three separately launchable variants are:

```text
BASELINE: Nav2 + DWB
LAYER:    Nav2 + DWB + UPO social layer in the local costmap (behavior FAIL)
CRITIC:   Nav2 + DWB + ProxemicForceCritic (Phase 6B PASS)
```

DWB remains the controller in all variants. Social MPC, MPPI, people-aware
global planning, and a custom controller are not included. The Phase 6B critic
uses only bounded proxemic cost and constant-velocity pedestrian prediction.

## External Dependencies

The Docker build uses unmodified, pinned upstream source revisions:

- `wg-perception/people`, ROS 2 branch, revision
  `0ae47f6e0208cedd84d19d066743fdc1d05fcafa`; only `people_msgs` is built.
- `robotics-upo/nav2_social_costmap_plugin`, Humble branch, revision
  `398a7e5e9937189a5a4b19000bc30a025421e103`.

`ros-humble-people-msgs` was not available from the Humble apt repository in
the project container, so the pinned source package is required. The two
packages built without patches against the existing ROS 2 Humble/Nav2
environment. The plugin produced three upstream unused-parameter compiler
warnings but no build errors.

The external overlay is installed at `/root/social_nav_ws/install` in the
image and sourced by the container shell.

## People Compatibility Boundary

The project boundary remains unchanged:

```text
/people     social_nav_msgs/msg/Pedestrians
```

The third-party-only compatibility path is:

```text
/people (social_nav_msgs/Pedestrians)
  -> social_people_bridge_node
  -> /people_nav2 (people_msgs/People)
  -> nav2_social_costmap_plugin::SocialLayer
```

The bridge copies only the fields needed by `people_msgs`:

| Source | Destination |
| --- | --- |
| message `header.stamp` | message `header.stamp` |
| message `header.frame_id` | message `header.frame_id` |
| `identifier` | `name` |
| `pose.position.x/y` | `position.x/y` |
| `velocity.linear.x/y` | `velocity.x/y` |
| constant | `reliability = 1.0` |

Position and velocity z values retain their zero message defaults. Optional
tag arrays remain empty. The bridge performs no tracking, filtering,
prediction, covariance handling, identity management, session logic, or
escort logic.

## Nav2 Configuration

The validated baseline remains:

```text
config/nav2_museum.yaml
launch/museum_navigation.launch.py
```

Neither baseline file is modified. Its local costmap contains
`obstacle_layer` and `inflation_layer`, and its controller is
`dwb_core::DWBLocalPlanner`.

The opt-in social variant uses:

```text
config/nav2_museum_social.yaml
launch/museum_navigation_social.launch.py
```

The global costmap and DWB configuration are copied unchanged from the
baseline. The only configuration addition is the local social layer between
the obstacle and inflation layers:

```yaml
plugins: [obstacle_layer, social_layer, inflation_layer]
social_layer:
  plugin: nav2_social_costmap_plugin::SocialLayer
  people_topic: /people_nav2
  enabled: true
  cutoff: 10.0
  amplitude: 200.0
  covariance_when_still: 0.8
  use_passing: false
  use_vel_factor: false
  publish_occgrid: true
```

The covariance was the one bounded adjustment made after the first run. No
DWB critic, global planner, escort threshold, or earlier-phase parameter was
tuned.

The accepted custom-critic variant uses:

```text
config/nav2_museum_social_force.yaml
launch/museum_navigation_social_force.launch.py
```

It starts from the baseline configuration, retains
`dwb_core::DWBLocalPlanner`, and keeps the baseline local costmap with only
`obstacle_layer` and `inflation_layer`. It adds only
`museum_social_critic::ProxemicForceCritic` to `FollowPath.critics`. It does
not load the UPO SocialLayer or require the `/people_nav2` bridge.

## Launch Commands

After starting TIAGo and Gazebo, choose exactly one Nav2 stack.

Baseline:

```bash
ros2 launch museum_assistant museum_navigation.launch.py
```

Social, in separate sourced terminals:

```bash
ros2 launch museum_assistant people.launch.py
ros2 launch museum_assistant social_people_bridge.launch.py
ros2 launch museum_assistant museum_navigation_social.launch.py
```

Accepted custom critic, in separate sourced terminals:

```bash
ros2 launch museum_assistant people.launch.py
ros2 launch museum_assistant museum_navigation_social_force.launch.py
```

Do not run the baseline and social Nav2 launches simultaneously. The social
launch does not start the reasoner, semantic navigation, visitor session,
escort script, people publisher, or bridge.

Useful checks:

```bash
ros2 topic echo --once /people
ros2 topic echo --once /people_nav2
ros2 topic echo --once /local_costmap/social_grid
ros2 param get /controller_server FollowPath.plugin
ros2 param get /controller_server local_costmap.plugins
```

## Build And Test Evidence

- Docker image build: passed.
- Unmodified `people_msgs` plus social-layer source build: passed.
- `colcon build --packages-select museum_social_critic museum_assistant`:
  passed.
- `colcon test --packages-select museum_social_critic museum_assistant`: 55
  tests passed, 0 failed, 0 skipped. This comprises 48 existing Python tests,
  six focused critic-math cases, and the CMake test wrapper.
- The bridge conversion helper has focused tests for name, position,
  velocity, header, empty input, and multiple pedestrians.

At runtime, the social stack reported
`nav2_social_costmap_plugin::SocialLayer`, subscription to `/people_nav2`, and
`dwb_core::DWBLocalPlanner`. The local plugin list was
`[obstacle_layer, social_layer, inflation_layer]`. `/people` still contained
`visitor_1`, `guide_1`, and `staff_1`, while `/people_nav2` contained the
corresponding compatibility messages.

The debug grid was published as `/local_costmap/social_grid`. A numeric sample
had 2,971 non-zero cells, maximum cost 199, and cost 199 at the guide cell.
This proves that the bridge and social layer generate proxemic costs from the
people stream.

## Runtime Comparison

All runs used the same initial TIAgO pose and the calibrated
`impressionism_hall` goal `(5.0, 1.5)`. Navigation and the automatic escort
sequence completed successfully.

The original static guide pose `(2.2, -0.35)` was too far from the nominal
route to exercise the social costs strongly:

| Variant | Result | Simulated navigation time | Minimum guide distance |
| --- | --- | ---: | ---: |
| Baseline | succeeded | 28.960 s | 1.077 m |
| Social, initial covariance | succeeded | 28.960 s | 1.071 m |
| Social, covariance 0.8 | succeeded | 38.725 s | 1.068 m |

A final controlled comparison temporarily moved the same visual-only
`guide_marker` to `(2.2, 0.15)` through Gazebo's runtime service. No world file
was changed, and the identical pose was used for both fresh runs:

| Variant | Result | Simulated navigation time | Wall time | Minimum guide distance |
| --- | --- | ---: | ---: | ---: |
| Baseline DWB | succeeded | 29.820 s | 70.451 s | 0.603 m |
| Social DWB + layer | succeeded | 28.835 s | 73.446 s | 0.604 m |

The 1 mm difference is simulation noise, not evidence of more personal space.
Therefore the required functional behavior comparison is **FAIL**, even
though plugin loading, data conversion, cost generation, navigation success,
and earlier-phase regression checks are **PASS**.

## Phase 6A DWB Diagnostic

The bounded Phase 6A experiment tested the hypothesis that DWB's generic
`BaseObstacle` critic was not sufficiently sensitive to the already-verified
social costs. Only the social Nav2 configuration was changed during each run;
the social layer, guide pose `(2.2, 0.15)`, robot start pose, semantic request,
goal, and all other critic weights remained unchanged.

Nav2 Humble declares the exact critic parameter as
`FollowPath.BaseObstacle.sum_scores`, with a default of `false`. The installed
implementation updates the trajectory score once per pose as
`score = sum_scores * score + pose_score`. Consequently, `false` replaces the
running value and returns the final sampled pose cost, while `true` accumulates
the cost of every sampled pose along the local trajectory. This behavior was
verified against the Humble `BaseObstacleCritic` source and the installed
`ros-humble-dwb-critics` package (`1.1.20-1jammy.20260607.083802`), and the
runtime controller parameter was confirmed as `true` for the experimental
runs.

Each candidate had a 120 simulated-second cutoff, more than four times the
29.820 s baseline. The cutoff distinguishes a usable navigation result from
the repeated no-progress and recovery loop observed during the experiment.
The values below are fresh controlled runs; an intermediate `0.20` run that
did not start at the exact original robot pose was discarded and repeated.

| Variant | `sum_scores` | `BaseObstacle.scale` | Result | Simulated time | Minimum guide distance |
| --- | ---: | ---: | --- | ---: | ---: |
| Recorded baseline DWB | false | 0.04 | succeeded | 29.820 s | 0.603 m |
| Recorded social run before Phase 6A | false | 0.04 | succeeded | 28.835 s | 0.604 m |
| Phase 6A social | true | 0.04 | timeout, no progress | 120.055 s | 2.206 m |
| Phase 6A social | true | 0.10 | timeout, no progress | 120.025 s | 2.205 m |
| Phase 6A social | true | 0.20 | timeout, no progress | 120.060 s | 2.205 m |
| Phase 6A social | true | 0.50 | timeout, no progress | 120.025 s | 2.205 m |

The approximately 2.205 m readings are the initial robot-to-guide distance,
not improved passing clearance: TIAGo remained effectively at the start pose.
The lowest tested scale already caused failure to make progress and repeated
recoveries; increasing the weight produced the same behavior rather than a
monotonic trajectory change. A likely explanation is that accumulating the
broad social costs over every local-trajectory pose penalizes all usable DWB
samples, including samples near the visitor at the robot, instead of creating
a discriminating lateral preference around the guide. This is an inference
from the observed controller behavior, not a separately proven plugin defect.

No experimental setting was selected. The social configuration was restored
to its pre-experiment state (`BaseObstacle.scale: 0.04`, implicit default
`sum_scores: false`). No post-selection regression run was applicable. The
validated baseline files were not modified, and the prior Phase 3, Phase 4,
Phase 5, and baseline Nav2 results remain the regression reference. During the
Phase 6A runs, the Phase 3 reasoning/semantic dispatch chain and Phase 5 people
stream continued to operate; navigation itself failed only under the rejected
experimental social settings.

Phase 6A behavioral acceptance therefore remains **FAIL**. The bounded generic
critic tuning experiment is closed. Phase 6B below implements the separately
reviewed dedicated critic; Social MPC was not started.

## Phase 6B Custom Proxemic Trajectory Critic

The small `ament_cmake` package `museum_social_critic` implements and exports
`museum_social_critic::ProxemicForceCritic` as a
`dwb_core::TrajectoryCritic`. This is inspired by proxemics, virtual repulsive
potentials, and social-force concepts. It is **not** the full Helbing Social
Force Model, Social MPC, a learned predictor, or a claim of research novelty.
Its project-specific contribution is to score DWB candidates directly from
pedestrian position and velocity.

The implementation was matched to the installed Nav2 Humble DWB API
(`dwb_core` 1.1.20): `onInit()` declares critic parameters and creates the
subscription; `prepare(pose, velocity, goal, plan)` prepares one control-cycle
snapshot; and `scoreTrajectory(Trajectory2D)` returns a raw score. DWB loads
the exact class from `FollowPath.ProxemicForce.class`, then applies the normal
critic `scale`.

`/people` is in `map`, while the rolling local costmap and DWB trajectory poses
are in `odom`. In each `prepare()` call the critic looks up one transform at
the people-message timestamp and applies it to all non-ignored positions and
velocity vectors. It stores only the latest message. Missing, stale, empty, or
untransformable people data clears the prepared set and contributes zero for
that cycle; it never rejects otherwise valid trajectories.

For trajectory sample time `t_i`, pedestrian prediction and clearance are:

```text
P_i = P_0 + V * t_i
d_i = ||R_i - P_i||
```

The bounded cost is:

```text
c(d_i) = 1 / (1 + exp((d_i - comfort_distance) / sigma))
raw trajectory score = max c(d_i) over all person/trajectory-pose pairs
```

Maximum aggregation represents the closest predicted encounter and avoids the
Phase 6A failure mode of accumulating a broad penalty across every trajectory
sample. Physical collision handling remains with Nav2.

The selected parameters are:

```yaml
comfort_distance: 1.0
sigma: 0.4
people_topic: /people
people_timeout: 1.0
ignored_identifiers: [visitor_1]
scale: 32.0
```

`visitor_1` is excluded from social scoring because the independent escort
supervisor answers “is my visitor still with me?” The critic answers “how
should I move around other people?” and considers `guide_1` and `staff_1`.
No Gazebo model name is hardcoded in the critic.

The technical gate passed: pluginlib discovered the exported XML, the
controller loaded the exact critic class while remaining
`dwb_core::DWBLocalPlanner`, and the critic logged three input pedestrians as
two considered plus one ignored. A no-people direct goal succeeded in 4.4 s,
and a people-enabled short goal succeeded while producing a non-zero raw
candidate-score range. This verifies both direct `/people` consumption and
baseline-like zero contribution when data is absent.

Only `ProxemicForce.scale` changed during the bounded four-value sweep. All
runs used the same start, semantic Impressionism goal, guide pose
`(2.2, 0.15)`, local costmap, DWB settings, and escort behavior:

| Scale | Result | Simulated navigation time | Minimum guide distance |
| ---: | --- | ---: | ---: |
| Recorded baseline | succeeded | 29.820 s | 0.603 m |
| 8 | succeeded | 28.810 s | 0.628 m |
| 16 | succeeded | 28.655 s | 0.633 m |
| **32** | **succeeded** | **28.820 s** | **0.665 m** |
| 64 | rejected: controller no-progress | not completed | not accepted |

Scale 32 increased minimum guide clearance by 0.062 m, or 10.3%, relative to
the controlled baseline. This is 62 times the 1 mm baseline/SocialLayer
difference previously classified as simulation noise. The closest observed
robot pose was approximately `(2.063, 0.801)` with the guide fixed at
`(2.2, 0.15)`. Motion remained stable, the critic reported non-zero and
trajectory-discriminating raw scores near the guide, and there were no
unexpected oscillations or recoveries. Scale 64 produced `Failed to make
progress` and was discarded without further tuning.

The accepted scale-32 run preserved the automatic escort sequence:

```text
navigation: accepted -> canceled -> accepted -> succeeded
escort:     escorting -> waiting -> escorting -> arrived
```

Phase 6B behavioral acceptance is therefore **PASS**. The optional moving
bystander runtime check was not needed; constant-velocity prediction is covered
by its focused unit test, and no additional moving-human framework was added.

## Regression Result

- Original baseline launch remains independent of the custom package behavior.
  A final baseline run used only the original DWB critic list and succeeded in
  28.915 simulated seconds.
- Phase 3 reasoning and semantic navigation still select and reach
  `impressionism_hall`.
- Phase 4 automatic `escorting -> waiting -> escorting -> arrived` behavior
  still completes under the baseline.
- Phase 5 `/people` still runs independently with its original message type.
- Phase 5 `/people` retained `social_nav_msgs/msg/Pedestrians`, the same three
  public identifiers, and position/velocity fields.
- The previous SocialLayer configuration and launch remain unchanged and
  opt-in. The new custom-critic configuration is a third, separate variant.

## Remaining Limitations

- Phase 6B is a one-scenario functional acceptance result, not a broad
  quantitative evaluation or general social-navigation guarantee.
- Only the selected scale-32 setting is accepted. Scale 64 demonstrated the
  upper failure boundary and must not be selected.
- People positions are Gazebo ground truth, not perception or tracking.
- One comparison is functional evidence only, not a quantitative evaluation.
- Social MPC and Phase 7 were not started.
