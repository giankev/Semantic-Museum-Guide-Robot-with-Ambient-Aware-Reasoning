# Known-Map Navigation With Nav2

This page records the geometric-navigation baseline originally completed as the known-map Nav2 milestone. It uses the saved SLAM map:

```text
exchange/museum_ws/src/museum_assistant/maps/museum_map.yaml
exchange/museum_ws/src/museum_assistant/maps/museum_map.pgm
```

Phase 3 adds the validated semantic-navigation path alongside the existing
manual goal tools. Phase 4 keeps the same Nav2/DWB stack and adds only
simulation-ground-truth escort supervision in the existing action owner.
Phase 6 adds a separate opt-in local social-costmap configuration while
preserving the original launch as the baseline.

## Current Status

Nav2 launches and lifecycle activation is automatic through `nav2_bringup` and lifecycle managers in `config/nav2_museum.yaml`.

Validated lifecycle state after launch:

- `/map_server`: active
- `/amcl`: active
- `/planner_server`: active
- `/controller_server`: active
- `/bt_navigator`: active
- `/behavior_server`: active

The BT XML path is fixed to:

```text
/opt/ros/humble/share/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml
```

`/navigate_to_pose` accepts goals, and Nav2 velocity commands reach TIAGo. The
complete Phase 3 chain reached `impressionism_hall` at `(5.0, 1.5)` and passed
its positive and non-moving negative acceptance tests. Other semantic poses
still require individual free-space verification.

`semantic_navigation_node` subscribes to `/museum/assistant_response` and sends
a goal only for a successful `recommend_and_prepare_navigation` decision using
the `navigate_to` skill. It publishes correlated JSON status updates on
`/museum/navigation_result`.

For Phase 4 the same node also subscribes to
`/museum/visitor_observation`, publishes `/museum/escort_state`, and may
intentionally cancel/resend its current goal when the simulated visitor lags
and recovers. Nav2 configuration, NavFn, costmaps, and DWB are unchanged. See
[Phase 4 Social Escort Supervision](social_escort.md).

## Launch TIAGo

Terminal 1:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant
source install/setup.bash
ros2 launch museum_assistant tiago_museum_world.launch.py
```

Wait until Gazebo opens, TIAGo is spawned, `/scan_raw` is publishing, and TF is available.

## Launch Nav2

Terminal 2:

```bash
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
cd /root/exchange/exchange/museum_ws
source install/setup.bash
ros2 launch museum_assistant museum_navigation.launch.py
```

This is the unchanged `Nav2 + DWB` baseline. To select the opt-in social
variant instead, start the people publisher and compatibility bridge in
separate terminals, then launch the social Nav2 stack:

```bash
source /root/social_nav_ws/install/setup.bash
ros2 launch museum_assistant people.launch.py
```

```bash
source /root/social_nav_ws/install/setup.bash
ros2 launch museum_assistant social_people_bridge.launch.py
```

```bash
source /root/social_nav_ws/install/setup.bash
ros2 launch museum_assistant museum_navigation_social.launch.py
```

The social selection is `Nav2 + DWB + local social layer`. Never run the two
Nav2 launches simultaneously. The social launch does not start the people
publisher, bridge, reasoner, semantic adapter, or escort script. See
[Human-Aware Navigation](human_aware_navigation.md) for schemas, parameters,
and the current non-passing behavioral comparison.

The launch uses:

- map frame: `map`
- odom frame: `odom`
- base frame: `base_footprint`
- scan topic: `/scan_raw`
- odometry topic reference: `/mobile_base_controller/odom`
- map: `museum_map.yaml`

If runtime TF inspection shows that TIAGo does not publish `base_footprint`, change `base_frame_id` and `robot_base_frame` values in `config/nav2_museum.yaml` to `base_link`.

## Lifecycle Check

Terminal 3:

```bash
docker exec -it museum_tiago bash -lc 'source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && for n in /map_server /amcl /planner_server /controller_server /bt_navigator /behavior_server; do echo "--- $n"; ros2 lifecycle get $n 2>/dev/null || true; done'
```

Expected: `/bt_navigator` should be `active [3]`, and the other listed lifecycle nodes should also be active.

## Set Initial Pose

Use this corrected `/initialpose` command near the museum entrance:

```bash
docker exec -it museum_tiago bash -lc 'source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped "{header: {frame_id: map}, pose: {pose: {position: {x: 0.0, y: 0.0, z: 0.0}, orientation: {z: 0.0, w: 1.0}}, covariance: [0.25, 0, 0, 0, 0, 0, 0, 0.25, 0, 0, 0, 0, 0, 0, 0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.068]}}"'
```

Check localization:

```bash
ros2 topic echo --once /amcl_pose
ros2 run tf2_ros tf2_echo map base_footprint
```

## Choose A Safe Goal

Do not assume arbitrary coordinates are valid. A point such as `(1.0, 0.0)` may be inside occupied, unknown, or inflated costmap space depending on the saved map and localization.

Preferred workflow:

1. Open RViz, or use the existing TIAGo/RViz window if available:

   ```bash
   ros2 run rviz2 rviz2
   ```

2. Set the RViz fixed frame to `map`.
3. Add displays for `/map`, `/global_costmap/costmap`, `/local_costmap/costmap`, `/scan_raw`, and TF.
4. Set or confirm the initial pose.
5. Pick a goal that is visibly in free space, not on a wall, not inside inflated costmap, and not behind an obstacle.
6. Start with a very short movement from the current robot pose before testing room-to-room goals.

Useful inspection commands:

```bash
ros2 topic echo --once /map
ros2 topic echo --once /amcl_pose
ros2 topic echo --once /global_costmap/costmap
ros2 topic echo --once /local_costmap/costmap
ros2 node list | grep -E "amcl|map_server|planner|controller|bt_navigator|costmap|lifecycle"
ros2 action list | grep navigate
```

## Calibrate Semantic Navigation Poses

Use calibrated AMCL poses for semantic rooms and artworks instead of guessed coordinates.

Workflow:

1. Launch TIAGo in the museum world.
2. Launch Nav2 and confirm lifecycle nodes are active.
3. Set or confirm the initial pose.
4. Use teleop to drive TIAGo to a safe stopping point for a room or artwork.
5. Capture the current localized pose:

   ```bash
   ros2 run museum_assistant capture_nav_pose --name impressionism_hall
   ```

6. Copy the printed `x`, `y`, and `yaw` values into the matching `nav_pose` entry in `config/semantic_map.yaml`, or store the snippet in a future navigation-goals file after review.
7. Test the captured coordinate with `send_nav_goal`.

Example output:

```yaml
impressionism_hall:
  nav_pose:
    x: 2.340
    y: -1.200
    yaw: 1.570
```

Use the captured coordinates with the helper:

```bash
ros2 run museum_assistant send_nav_goal --x 2.340 --y -1.200 --yaw 1.570
```

This calibration step is the bridge between the semantic identifiers in `semantic_map.yaml` and valid Nav2 `NavigateToPose` goals on the saved museum map.

## Send A Manual Goal

Use this only after selecting a point that appears free in the map/costmap view:

```bash
docker exec -it museum_tiago bash -lc 'source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose "{pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.0, z: 0.0}, orientation: {w: 1.0}}}}" --feedback'
```

If this point aborts with `failed to create plan`, choose a visibly free point in RViz rather than repeatedly using the same coordinate.

## Helper Goal Command

The package provides a lightweight helper around the Nav2 `NavigateToPose` action:

```bash
docker exec -it museum_tiago bash -lc 'source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && cd /root/exchange/exchange/museum_ws && source install/setup.bash && ros2 run museum_assistant send_nav_goal --x 1.0 --y 0.0 --yaw 0.0'
```

The helper prints whether the goal was accepted, succeeded, aborted, or canceled, including elapsed time after acceptance.

## Interpreting Results

- `Goal accepted`: the Nav2 action server accepted the request. It does not mean a valid path exists.
- `Goal rejected`: usually lifecycle, BT navigator, or action-server readiness problem.
- `Goal aborted`: Nav2 accepted the goal but failed during planning, control, or recovery.
- `failed to create plan`: the planner could not find a valid path to the requested goal. The goal may be occupied, unknown, inflated, outside the map, or disconnected from the robot's current pose.
- `Collision Ahead`: a recovery behavior or local controller believes the robot path is blocked. Check the local costmap and laser scan.
- `SUCCEEDED but very slow`: Nav2 is working but tuning remains poor. This is acceptable for the current baseline, but not final.

## Troubleshooting

- If `/bt_navigator` is inactive, check the BT XML path. It must use `navigate_to_pose_w_replanning_and_recovery.xml`.
- If goals are accepted but abort immediately, inspect `/global_costmap/costmap` and choose a goal in clearly free space.
- If the robot barely moves, inspect `/local_costmap/costmap`, `/scan_raw`, AMCL pose, and TF.
- If recoveries repeat, reset the initial pose and test a shorter goal.
- If planning fails near the robot, the robot may be localized inside an occupied or inflated region.

## Current Limitations

- Semantic execution passed the complete Phase 3 runtime acceptance for
  `impressionism_hall`; the remaining room poses are not all runtime-accepted.
- Manual goals remain available through the Nav2 action interface and helper
  CLI.
- Escort monitoring is a one-visitor Gazebo-ground-truth prototype with a
  static marker moved manually or by the opt-in lag-recovery script.
- The standard simulation `/people` stream remains the public boundary. An
  opt-in bridge and local social layer consume it only in the social variant.
- No Interaction Manager, Behavior Executive, real perception, LLM, speech,
  or vision is included.
- Baseline DWB has no people-aware costs. The opt-in DWB variant receives
  social local-costmap costs, but has not demonstrated a meaningful clearance
  or trajectory change yet.
- Every semantic room pose other than the accepted Impressionism goal still
  needs free-space calibration.

## Architectural Next Steps

The current system intentionally uses one direct, tightly filtered adapter
instead of introducing unused task-management layers. Remaining work includes:

1. calibrate each remaining final-demo semantic pose with `capture_nav_pose`;
2. keep plain recommendations non-moving;
3. repeat the documented automatic or manual escort scenarios where
   evaluation evidence is required;
4. resolve the documented Phase 6 behavioral acceptance gap before adding a
   different controller or real people tracking.

See [Architecture](architecture.md) and [Repository Audit](repository_audit.md).
