# Deterministic Reasoning Node

Milestone 5 adds structured request reasoning without LLMs, Nav2, or robot control.

`/museum/user_request` carries JSON strings that simulate the future output of an LLM parser. A request contains a `request_id`, an `intent`, and optional semantic constraints:

```json
{
  "request_id": "req_001",
  "intent": "recommend",
  "constraints": {
    "style": "impressionism",
    "avoid_crowd": true,
    "child_friendly": false,
    "wheelchair_accessible": true
  }
}
```

Supported intents are `recommend` and `recommend_and_prepare_navigation`. Supported constraints are `style`, `avoid_crowd`, `child_friendly`, and `wheelchair_accessible`.

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
```

This prepares for later LLM integration by defining the structured JSON interface the parser must produce. It prepares for Nav2 by returning an abstract `navigate_to` skill and semantic-map `nav_pose`, but it does not execute navigation yet.
