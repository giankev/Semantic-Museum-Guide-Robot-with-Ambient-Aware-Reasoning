# Phase 5 Simulated People Stream

## Scope

Phase 5 adds one opt-in simulation adapter from Gazebo model states to the
standard ROS 2 `/people` stream. It is simulation ground truth, not perception,
tracking, or engagement detection. Baseline DWB and the validated Phase 4
escort interfaces are unchanged.

```text
/gazebo/model_states -> simulated_people_node
                     -> /people (social_nav_msgs/msg/Pedestrians)
```

`/people` remains the public input boundary for human-aware navigation. The
optional Phase 6 compatibility bridge consumes it and republishes
`people_msgs/msg/People` on `/people_nav2` only because the selected
third-party costmap layer requires that older message. See
[Human-Aware Navigation](human_aware_navigation.md). Escort still does not
consume `/people`.

## Verified Standard Message

The base Docker image did not initially contain `social_nav_msgs`. After
refreshing the normal ROS Humble APT catalog, the official package was
available as `ros-humble-social-nav-msgs` version
`0.1.0-1jammy.20260605.123506`. The Dockerfile and package manifest now declare
only this additional message dependency.

The runtime commands report `/opt/ros/humble` and the following exact schemas:

```text
$ ros2 interface show social_nav_msgs/msg/Pedestrian
string identifier
geometry_msgs/Pose2D pose
        float64 x
        float64 y
        float64 theta
nav_2d_msgs/Twist2D velocity
        float64 x
        float64 y
        float64 theta

$ ros2 interface show social_nav_msgs/msg/Pedestrians
std_msgs/Header header
        builtin_interfaces/Time stamp
                int32 sec
                uint32 nanosec
        string frame_id
social_nav_msgs/Pedestrian[] pedestrians
        string identifier
        geometry_msgs/Pose2D pose
                float64 x
                float64 y
                float64 theta
        nav_2d_msgs/Twist2D velocity
                float64 x
                float64 y
                float64 theta
```

## Simulated People And Identity Boundary

Runtime `/gazebo/model_states` inspection verified these current models:

| Internal Gazebo model | Public identifier |
| --- | --- |
| `visitor_marker` | `visitor_1` |
| `guide_marker` | `guide_1` |
| `staff_marker` | `staff_1` |

`tiago` is explicitly outside the mapping and is never published as a
pedestrian. Gazebo model names do not appear in `/people`.

## Frame Validation

The publisher uses `header.frame_id=map` only after checking the current
runtime alignment at two stabilized TIAGo poses:

| Sample | Gazebo `world` x/y | TF `map -> base_footprint` x/y | Difference |
| --- | --- | --- | ---: |
| Entrance | `(-0.0005, 0.0001)` | approximately `(0.000, 0.000)` | below 1 mm |
| Moved pose | `(0.4205, 0.0114)` | `(0.457, 0.015)` | approximately 3.7 cm |

The small second difference is consistent with AMCL localization error rather
than a frame offset or rotation. The museum map and Gazebo world therefore
share the same effective planar frame and no extra transform is applied.

## Velocity Estimate

`ModelStates` has no header, so each callback is stamped with the node's ROS
simulation clock. For every available person:

```text
vx = (x_now - x_previous) / dt
vy = (y_now - y_previous) / dt
```

The first observation and any non-finite or non-positive `dt` produce zero
velocity. A missing model loses its previous sample, so a later reappearance
also begins at zero. `velocity.theta` is zero because Phase 5 estimates only
the requested planar translational velocity. No filtering, prediction,
acceleration, or trajectory history is added.

## Commands

Build the image after adding the standard message dependency:

```bash
docker build -t museum-tiago:humble \
  -f dockerfiles/Dockerfile.tiago_museum .
```

Build and source the workspace inside the container, then launch the world and
the opt-in publisher in separate terminals:

```bash
ros2 launch museum_assistant tiago_museum_world.launch.py
ros2 launch museum_assistant people.launch.py
ros2 topic echo /people
```

Without `scripted_visitor_node`, all three reported velocities should remain
approximately zero. To see `visitor_1` move and confirm the escort remains
unchanged, start the existing full demo:

```bash
ros2 launch museum_assistant museum_navigation.launch.py
ros2 launch museum_assistant visitor_session.launch.py
ros2 run museum_assistant reasoning_node
ros2 launch museum_assistant semantic_navigation.launch.py
ros2 launch museum_assistant scripted_visitor.launch.py
ros2 launch museum_assistant people.launch.py
```

Then send:

```bash
ros2 topic pub --once /museum/user_request std_msgs/msg/String \
  "{data: '{\"request_id\":\"phase5_people_demo_001\",\"session_id\":\"session_1\",\"intent\":\"recommend_and_prepare_navigation\",\"constraints\":{\"style\":\"impressionism\"}}'}"
```

The accepted Phase 4 sequence must remain:

```text
escort:     escorting -> waiting -> escorting -> arrived
navigation: accepted  -> canceled -> accepted  -> succeeded
```

The runtime acceptance run with request `phase5_people_demo_001` observed that
exact sequence. Before scripted motion, `/people` reported all three markers
with zero velocity. During visitor recovery it reported `visitor_1` at
`(2.8748, 0.7294)` with `(vx, vy)=(0.2468, 0.0996)` m/s while `guide_1` and
`staff_1` remained at zero. After `arrived`, `visitor_1` stopped at
`(3.2143, 0.8595)` and all three velocities were zero again. Every sample used
`header.frame_id=map`, and only the three public identifiers above appeared.

Omit `people.launch.py` to run the previous project exactly as before.

The ROS-independent package test suite contains seven Phase 5 velocity and
identity cases. The complete package run passed 42 tests after this adapter was
added.

## Limitations

- The accepted samples in this document use the lightweight baseline museum.
  Marker names and public IDs are preserved in the supplied scene, but
  supplied-world `/people` runtime acceptance is blocked behind its unresolved
  occupancy-map/navigation gate.
- All data is Gazebo ground truth from three marker models.
- Velocity is a finite difference at the model-state observation rate.
- There is no confidence, covariance, prediction, re-identification, or
  engagement state.
- The marker script has no obstacle avoidance or human motion model.
- Escort does not consume `/people`; it retains its validated Phase 4 input.
- Baseline DWB does not consume `/people`. The opt-in social-costmap variant
  uses it through the compatibility bridge, but behavioral runtime acceptance
  remains open.
