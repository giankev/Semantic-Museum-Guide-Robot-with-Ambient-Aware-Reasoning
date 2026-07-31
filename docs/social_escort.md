# Phase 4 Social Escort Supervision

## Scope

Phase 4 adds one minimal escort supervisor using Gazebo simulation ground
truth. It is not real person perception and it is not social navigation. Nav2,
AMCL, NavFn, and the DWB local controller are unchanged.

The static `visitor_marker` and TIAGo poses are read only by
`visitor_session_node`. Simulator model names stop at that adapter. The public
flow is:

```text
/gazebo/model_states -> visitor_session_node
                     -> /museum/visitor_observation
                     -> semantic_navigation_node
                     -> existing NavigateToPose owner
                     -> /museum/navigation_result
                     -> /museum/escort_state
```

## Public Visitor Observation

`/museum/visitor_observation` uses `std_msgs/String` JSON. A present visitor
has a planar distance from TIAGo:

```json
{
  "session_id": "session_1",
  "track_id": "visitor_1",
  "present": true,
  "distance_to_robot": 1.8
}
```

When the configured visitor model is absent, `distance_to_robot` is omitted:

```json
{
  "session_id": "session_1",
  "track_id": "visitor_1",
  "present": false
}
```

No simulator model name, velocity, heading, confidence, prediction, or vision
field is published.

## Escort State Machine

`escort.py` is ROS-independent and has only four public states:

- `escorting`: an escort task is active and Nav2 may move TIAGo;
- `waiting`: the visitor is lagging, or TIAGo reached the destination before
  the visitor;
- `lost`: the visitor is absent too long or beyond the lost distance; terminal
  for the current task;
- `arrived`: TIAGo reached the Nav2 destination and the visitor is within the
  arrival distance; terminal success.

The supervisor is inactive outside an escort task. Default ROS parameters on
`semantic_navigation_node` are:

| Parameter | Default |
| --- | ---: |
| `resume_distance` | 2.0 m |
| `wait_distance` | 3.0 m |
| `lost_distance` | 8.0 m |
| `arrival_distance` | 2.5 m |
| `wait_delay` | 3.0 s |
| `absence_timeout` | 3.0 s |

The node rejects invalid distance ordering; it requires
`resume_distance < wait_distance < lost_distance`. A distance above 3.0 m must
persist for 3.0 s before `ESCORTING -> WAITING`. `WAITING -> ESCORTING` occurs
only at or below 2.0 m, which supplies hysteresis. A distance at or above
8.0 m causes `LOST` immediately. Visitor absence causes `LOST` after 3.0 s.

## Pause, Resume, And Results

`semantic_navigation_node` remains the only owner of `NavigateToPose`. It
stores only the current pose and correlation fields needed for one task.

- `ESCORTING -> WAITING`: request cancellation of the active Nav2 goal.
- An intentional pause still publishes low-level
  `/museum/navigation_result` status `canceled`, but the semantic task remains
  in memory.
- `WAITING -> ESCORTING`: resend the same stored pose after the canceled goal
  has finished. There is no queue or preemption.
- `LOST`: cancel any active goal and never resume it automatically.
- External/final cancellation has no internal pause marker, so it terminates
  the task instead of being eligible for resend.

`/museum/navigation_result` retains its Phase 3 meaning: it reports the
low-level Nav2 result. Nav2 `succeeded` means only that TIAGo reached the pose.

`/museum/escort_state` is also `std_msgs/String` JSON:

```json
{
  "request_id": "phase4_demo_001",
  "session_id": "session_1",
  "selected_room": "impressionism_hall",
  "state": "waiting",
  "distance_to_robot": 3.6
}
```

The same correlation fields are present on terminal success:

```json
{
  "request_id": "phase4_demo_001",
  "session_id": "session_1",
  "selected_room": "impressionism_hall",
  "state": "arrived",
  "distance_to_robot": 1.7
}
```

`ARRIVED`, not Nav2 `succeeded`, is Phase 4 task success. When Nav2 succeeds
with a visitor farther than 2.5 m, the escort stays `waiting`; bringing the
visitor within 2.5 m changes it to `arrived` without sending another goal.

## Verified Gazebo Interface

Runtime inspection of the current museum launch found these model names:

```text
visitor_marker
tiago
```

They are the defaults of the simulation adapter parameters
`visitor_model_name` and `robot_model_name`. They do not appear in public
observations or escort logic.

The current `libgazebo_ros_state.so` plugin provides both verified services:

```text
/gazebo/get_entity_state
/gazebo/set_entity_state
```

The following command was verified to reposition the static visitor marker:

```bash
ros2 service call /gazebo/set_entity_state gazebo_msgs/srv/SetEntityState \
  "{state: {name: visitor_marker, pose: {position: {x: 3.9, y: 1.2, z: 0.0}, orientation: {w: 1.0}}, reference_frame: world}}"
```

Inspect TIAGo before choosing a nearby marker pose:

```bash
ros2 service call /gazebo/get_entity_state gazebo_msgs/srv/GetEntityState \
  "{name: tiago, reference_frame: world}"
```

Useful verified marker poses for the current world are:

- near the entrance: `(0.25, -0.45)`;
- recovered/near the Impressionism route: `(3.9, 1.2)`;
- lost from the Impressionism Hall: `(-3.0, -5.0)`, measured at about 9.94 m
  in the runtime check.

## Exact Manual Acceptance Demo

Build the package, source the workspace in every terminal, then start these
existing processes separately:

```bash
ros2 launch museum_assistant tiago_museum_world.launch.py
ros2 launch museum_assistant museum_navigation.launch.py
ros2 launch museum_assistant visitor_session.launch.py
ros2 run museum_assistant reasoning_node
ros2 launch museum_assistant semantic_navigation.launch.py
```

Confirm the public inputs and outputs:

```bash
ros2 topic echo /museum/visitor_observation
ros2 topic echo /museum/navigation_result
ros2 topic echo /museum/escort_state
```

### A-C: Escort, Wait, And Resume

Reset the marker to its world pose:

```bash
ros2 service call /gazebo/set_entity_state gazebo_msgs/srv/SetEntityState \
  "{state: {name: visitor_marker, pose: {position: {x: 0.25, y: -0.45, z: 0.0}, orientation: {w: 1.0}}, reference_frame: world}}"
```

Send one executable request:

```bash
ros2 topic pub --once /museum/user_request std_msgs/msg/String \
  "{data: '{\"request_id\":\"phase4_demo_001\",\"session_id\":\"session_1\",\"intent\":\"recommend_and_prepare_navigation\",\"constraints\":{\"style\":\"impressionism\"}}'}"
```

Expected sequence:

1. `/museum/escort_state` reports `escorting` and Nav2 reports `accepted`.
2. Leave the static marker at the entrance. Once its distance stays above
   3.0 m for 3.0 s, escort state becomes `waiting`, Nav2 reports the
   intentional `canceled`, and TIAGo stops.
3. Move the marker near the stopped robot. In the verified run TIAGo stopped
   near `(3.93, 1.22)`, so this command reproduced recovery:

   ```bash
   ros2 service call /gazebo/set_entity_state gazebo_msgs/srv/SetEntityState \
     "{state: {name: visitor_marker, pose: {position: {x: 3.9, y: 1.2, z: 0.0}, orientation: {w: 1.0}}, reference_frame: world}}"
   ```

4. Escort state returns to `escorting`, the same semantic pose is accepted
   again, and TIAGo continues. The verified episode ended with Nav2
   `succeeded` followed by escort `arrived`.

### D: Lost Is Terminal

After the first episode, place the marker beyond the lost threshold:

```bash
ros2 service call /gazebo/set_entity_state gazebo_msgs/srv/SetEntityState \
  "{state: {name: visitor_marker, pose: {position: {x: -3.0, y: -5.0, z: 0.0}, orientation: {w: 1.0}}, reference_frame: world}}"
```

Start a different semantic goal:

```bash
ros2 topic pub --once /museum/user_request std_msgs/msg/String \
  "{data: '{\"request_id\":\"phase4_demo_lost_001\",\"session_id\":\"session_1\",\"intent\":\"recommend_and_prepare_navigation\",\"constraints\":{\"style\":\"classical\"}}'}"
```

The verified result selected `ancient_art_hall`, accepted the goal, changed to
`lost`, canceled Nav2, and did not resume. Restore the marker afterward with
the entrance-pose command above.

### E: Clean Joint Arrival

Restart the simulation for a clean episode. Send `phase4_demo_001`, but move
the marker forward before it remains more than 3.0 m behind. For the current
route, `(2.0, 0.0)` in the corridor followed by `(3.9, 1.2)` near the
destination are practical manual checkpoints. The required terminal evidence
is:

```text
/museum/navigation_result: succeeded
/museum/escort_state: arrived
```

To demonstrate that navigation success is not escort success, instead leave
the visitor more than 2.5 m from the destination until Nav2 succeeds. Escort
state remains `waiting`. Move the marker within 2.5 m and verify `arrived`
appears without a new `accepted` navigation result.

## Limitations

- Observations use Gazebo ground truth, not perception.
- `visitor_marker` is static and moved manually; there is no moving-person
  framework.
- Only one visitor, one session, and one escort task are supported.
- `LOST` has no automatic or dialogue recovery.
- DWB is unchanged; there are no people-aware costs or social-navigation
  behaviors.
- There is no Interaction Manager, Behavior Executive, task scheduler, LLM,
  speech, or persistent session memory.
