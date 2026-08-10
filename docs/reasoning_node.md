# Deterministic Structured-Request Reasoning

This page records the deterministic structured-request milestone. Phase 3 adds
a separate focused consumer that can send explicitly prepared successful
decisions to the existing Nav2 baseline.

`museum_assistant/contracts.py` now defines the ROS-independent
`StructuredRequest` and `ReasoningDecision` boundaries used by the deterministic
reasoner. Dictionary/JSON input is validated into a contract object before
semantic reasoning, then the typed decision is serialized back to the existing
response schema.

`/museum/user_request` carries JSON strings that simulate the future output of an LLM parser. A request contains a `request_id`, an `intent`, and optional semantic constraints:

```json
{
  "request_id": "req_001",
  "intent": "recommend",
  "constraints": {
    "style": "impressionism",
    "avoid_crowd": true,
    "avoid_noise": true,
    "child_friendly": false,
    "wheelchair_accessible": true
  }
}
```

A request may also carry an optional session:

```json
{
  "request_id": "req_001",
  "session_id": "session_001",
  "intent": "recommend",
  "constraints": {"style": "impressionism"}
}
```

Requests without `session_id` remain valid and produce the original response
shape. When provided, the validated session ID is copied into the reasoning
response for correlation only; the reasoner does not manage session state.

Supported intents are `recommend` and `recommend_and_prepare_navigation`.
Supported constraints are `style`, `avoid_crowd`, `avoid_noise`,
`child_friendly`, and `wheelchair_accessible`. `avoid_noise: true` rejects a
room only when its current `noise_level` is `high`, with the explicit rejection
reason `noise_level_high`.

`/museum/assistant_response` carries JSON strings with the deterministic result. A successful response includes the selected room, display name, abstract skill `navigate_to`, navigation pose from the semantic map, explanation, matching artworks, and rejected rooms. If no room matches, the response uses `status: no_match` and skill `ask_clarification`. Invalid input produces `status: invalid_request`.

Run the demo inside the Docker container:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant
source install/setup.bash
ros2 launch museum_assistant reasoning_demo.launch.py
```

Manual request:

```bash
ros2 topic pub --once /museum/user_request std_msgs/msg/String "{data: '{\"request_id\":\"manual_001\",\"intent\":\"recommend\",\"constraints\":{\"style\":\"impressionism\",\"avoid_crowd\":true}}'}"
```

Inspect responses:

```bash
ros2 topic echo /museum/assistant_response
ros2 topic echo /museum/scene_graph
```

This interface can later receive output from a deterministic natural-language
parser or controlled LLM fallback. It returns an abstract `navigate_to` skill
and semantic-map `nav_pose`. `semantic_navigation_node` consumes only successful
`recommend_and_prepare_navigation` responses; no Interaction Manager, Behavior
Executive, or escort runtime exists. The current request simulator is not
natural-language interaction.

The semantic room ID remains the authoritative decision target. During the
minimal Phase 3 prototype, the navigation adapter uses the deterministic
`nav_pose` already copied from the semantic map. It never accepts coordinates
from the user request, and every demo pose still requires occupancy-map
calibration.

## Phase 1 Tests

Run without Gazebo, Nav2, or a ROS graph:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --packages-select museum_assistant
colcon test --packages-select museum_assistant
colcon test-result --verbose
```
