# Phase 6 Minimal Human-Aware Navigation Variant

## Status

The opt-in technical integration is implemented and runs, but Phase 6 is not
runtime-accepted yet. Both baseline and social navigation reached the goal,
the social layer consumed the converted people stream, and non-zero social
costs were measured. The controlled comparison did not show a meaningful
increase in robot-bystander distance or a visibly different local trajectory.

The two variants are:

```text
BASELINE: Nav2 + DWB
SOCIAL:   Nav2 + DWB + UPO social layer in the local costmap
```

DWB remains the controller in both variants. Social MPC, MPPI, prediction,
people-aware global planning, and a custom social controller are not included.

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
- `colcon build --packages-select museum_assistant`: passed.
- `colcon test --packages-select museum_assistant`: 48 passed, 0 failed,
  0 skipped.
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

## Regression Result

- Original baseline launch works without people publisher, bridge, or social
  layer.
- Phase 3 reasoning and semantic navigation still select and reach
  `impressionism_hall`.
- Phase 4 automatic `escorting -> waiting -> escorting -> arrived` behavior
  still completes under the baseline.
- Phase 5 `/people` still runs independently with its original message type.
- Social navigation remains opt-in.

## Remaining Limitations

- Phase 6 must not be described as runtime-validated until the social variant
  produces a repeatable local-trajectory or clearance change without breaking
  navigation.
- The existing DWB baseline gives obstacle costs a deliberately low weight;
  resolving the missing behavioral effect requires a separately reviewed,
  bounded experiment rather than undocumented parameter tuning.
- People positions are Gazebo ground truth, not perception or tracking.
- One comparison is functional evidence only, not a quantitative evaluation.
- Social MPC and Phase 7 were not started.
