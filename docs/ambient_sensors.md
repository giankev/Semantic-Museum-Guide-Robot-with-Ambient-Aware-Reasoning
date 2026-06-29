# Ambient Sensor Simulation

`/museum/ambient_state` represents dynamic museum predicates that can change while TIAGo is running: room crowd level, room noise level, and whether a room is open or closed. Messages are JSON strings published as `std_msgs/msg/String`.

Ambient state is simulated so the semantic graph can be tested before real museum sensors or perception modules exist. The simulator publishes a deterministic scenario, and `semantic_graph_node` applies each update to the in-memory semantic graph. After every update it recomputes a recommendation, showing how semantic reasoning changes when the environment changes.

Run inside the Docker container:

```bash
cd /root/exchange/exchange/museum_ws
colcon build --symlink-install --packages-select museum_assistant
source install/setup.bash
ros2 launch museum_assistant ambient_reasoning.launch.py
```

This milestone does not include Nav2, LLM reasoning, vision, custom ROS2 messages, or persistent semantic-state storage. The dynamic state is held in memory by the semantic graph node.
