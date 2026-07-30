# Known-Map Navigation With Nav2

This page records the geometric-navigation baseline originally completed as the known-map Nav2 milestone. It uses the saved SLAM map:

```text
exchange/museum_ws/src/museum_assistant/maps/museum_map.yaml
exchange/museum_ws/src/museum_assistant/maps/museum_map.pgm
```

Phase 3 adds a focused semantic-navigation prototype alongside the existing
manual goal tools.

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

`/navigate_to_pose` accepts goals, and Nav2 velocity commands reach TIAGo. Some map coordinates still abort during planning or recovery, so treat this as a working but not fully tuned Nav2 baseline.

`semantic_navigation_node` subscribes to `/museum/assistant_response` and sends
a goal only for a successful `recommend_and_prepare_navigation` decision using
the `navigate_to` skill. It publishes correlated JSON status updates on
`/museum/navigation_result`. Full runtime acceptance of that new path is still
pending.

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

- Semantic execution exists as a focused prototype but has not completed the
  full simulator acceptance workflow.
- Manual goals remain available through the Nav2 action interface and helper
  CLI.
- No Interaction Manager, Behavior Executive, escort, LLM, or vision is
  included.
- Navigation is functional but still unstable for some goals and map regions.
- Every semantic room pose still needs free-space calibration.

## Architectural Next Steps

Phase 3 intentionally uses one direct, tightly filtered adapter instead of
introducing unused task-management layers. The next work is to:

1. validate the complete reasoning-to-Nav2 path in simulation;
2. calibrate each final-demo semantic pose with `capture_nav_pose`;
3. keep plain recommendations non-moving;
4. leave Interaction Manager, Behavior Executive, and escort policies for
   milestones that actually require them.

See [Architecture](architecture.md) and [Repository Audit](repository_audit.md).
