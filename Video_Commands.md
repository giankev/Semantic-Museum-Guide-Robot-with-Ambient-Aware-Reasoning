# Museum Demo - Complete Video Commands

## 0. Start Docker

### Terminal 1 - Host

Open a normal terminal on the host:

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

> If the container is not running yet, start it first:

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
./start_museum_tiago.sh
```

Then, from another host terminal:

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

---

# 1. Build the workspace

### Terminal 1 - Inside Docker

```bash
cd /root/exchange/exchange/museum_ws
```

If this is a fresh/dirty build:

```bash
rm -rf build install log
```

Build:

```bash
colcon build --symlink-install --packages-select museum_assistant
```

Source:

```bash
source install/setup.bash
```

---

# 2. Start the actual supplied museum

### Terminal 1 - Inside Docker

This is the main Gazebo scene for the demo:

```bash
ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py gzclient:=True
```

Wait for **Gazebo + the museum + TIAGo + Nav2** to come up.

The supplied museum uses the detailed museum visual environment together with a simplified navigation/collision representation and the generated 2D occupancy map. 

---

# 3. Open the other terminals

For **every additional terminal**, first open a terminal on the host and enter the running container.

## Terminal 2 - Assistant response

### Host

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

### Inside Docker

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/assistant_response
```

---

## Terminal 3 - Navigation result

### Host

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

### Inside Docker

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/navigation_result
```

---

## Terminal 4 - Session state

### Host

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

### Inside Docker

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/session_state
```

---

## Terminal 5 - Escort state

### Host

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

### Inside Docker

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/escort_state
```

---

## Terminal 6 - Ambient state

### Host

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

### Inside Docker

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/ambient_state
```

---

# 4. Video - Visitor detection

### What to show

* Gazebo museum
* TIAGo inside the museum
* Visitor approaches the robot
* Visitor enters the robot's camera FOV
* Visitor stops in front of the robot
* Hold the shot for several seconds

The engagement pipeline combines RGB person detection with frontal LiDAR. A person must be close enough, remain in the relevant camera region, and dwell for at least 2.5 seconds with low radial velocity to reach `ENGAGED`. 

### Useful terminal

Terminal 7:

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

Inside:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/engagement_state
```

If your implementation exposes the engagement state under a different topic, use the topic actually present in the running system.

---

# 5. Video - Speech request

The project uses a **pre-recorded WAV file** for speech input. This is intentional: the implemented speech interface accepts an audio-file path through `/museum/audio_file`, rather than a live microphone stream. 

Use the supplied example:

```text
/root/exchange/impressionism.wav
```

## Terminal 7 - Speech-to-text

### Host

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

### Inside Docker

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 launch museum_assistant speech_to_text.launch.py
```

---

## Terminal 8 - Play/send the WAV

### Host

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

### Inside Docker

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic pub --once /museum/audio_file std_msgs/msg/String \
"{data: '/root/exchange/impressionism.wav'}"
```

The pipeline is:

```text
WAV
 ↓
Speech-to-text / Whisper
 ↓
Language understanding
 ↓
Structured request
 ↓
Semantic reasoning
```

The language model is only a bounded language-understanding fallback; it does **not** choose navigation coordinates or directly control the robot. 

---

# 6. Video - Direct semantic reasoning demo

If you want to skip speech and demonstrate the reasoning system directly, publish the structured request.

## Terminal 8 - Semantic request

### Host

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

### Inside Docker

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash

ros2 topic pub --once /museum/user_request std_msgs/msg/String \
"{data: '{\"request_id\":\"nav_demo_001\",\"session_id\":\"session_1\",\"intent\":\"recommend_and_prepare_navigation\",\"constraints\":{\"style\":\"impressionism\"}}'}"
```

Expected reasoning:

```text
request
   ↓
style = impressionism
   ↓
semantic museum graph
   ↓
candidate locations
   ↓
impressionism_hall
   ↓
semantic route
   ↓
physical route
   ↓
Nav2
```

The project's documented mapping includes:

```text
impressionism_hall → north_gallery
```



---

# 7. Video - Ambient-aware reasoning

The semantic graph also contains dynamic ambient information such as crowd level, noise, and whether rooms are open. The reasoner evaluates the request against these changing conditions. 

## Terminal 9 - Publish an ambient change

### Host

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

### Inside Docker

First inspect the current topic:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/ambient_state
```

For the exact JSON format expected by the running ambient node, inspect the project's configuration/node implementation before recording:

```bash
grep -R "ambient_state" -n /root/exchange/exchange/museum_ws/src/museum_assistant
```

Then publish the ambient condition using the format expected by that node.

### Video scenario

Show:

```text
Visitor request
      ↓
"impressionism"
      ↓
Initial semantic decision
      ↓
Museum becomes crowded/noisy
      ↓
Ambient state update
      ↓
Reasoner reevaluates
      ↓
Different valid destination
```

This is one of the strongest demonstrations of the project because the semantic graph is explicitly designed to combine static museum knowledge with dynamic ambient state. 

---

# 8. Video - Session memory

## Terminal 10 - Session state

### Host

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

### Inside Docker

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
ros2 topic echo /museum/session_state
```

Then demonstrate:

```text
First interaction
      ↓
session_1
      ↓
visitor preference stored
      ↓
follow-up request
      ↓
"take me there / here"
      ↓
previous destination recovered
      ↓
destination revalidated against current ambient state
```

The session memory is represented in the semantic graph and stores bounded information such as the visitor's previous intent/preferences. 

---

# 9. Video - Escorting

The supplied museum reasoning launch already provides the components needed for the integrated escort demonstration.

### Terminal 5

Keep this running:

```bash
ros2 topic echo /museum/escort_state
```

### Video

Show:

```text
Visitor request
      ↓
Robot receives destination
      ↓
ESCORTING
      ↓
TIAGo starts moving
      ↓
Visitor follows
      ↓
Gazebo + RViz show navigation
```

The escort supervisor has four states:

```text
ESCORTING
WAITING
LOST
ARRIVED
```

The important recovery transition is:

```text
ESCORTING
    ↓
visitor > 3 m for 3 s
    ↓
WAITING
    ↓
visitor ≤ 2 m
    ↓
ESCORTING
```



---

# 10. Video - Visitor falls behind

This is a good separate ~1 minute scenario.

### Video

Let the robot start escorting.

Then:

```text
Robot moves forward
       ↓
Visitor remains behind
       ↓
distance > 3 m
       ↓
WAITING
       ↓
robot stops
```

Watch:

```bash
ros2 topic echo /museum/escort_state
```

You should see:

```text
ESCORTING
WAITING
```

The route runner cancels the active Nav2 goal when the visitor falls behind. 

---

# 11. Video - Visitor catches up

Continue from the previous scenario.

Move/allow the visitor to approach the robot again.

When the visitor comes back within 2 m:

```text
WAITING
   ↓
visitor ≤ 2 m
   ↓
ESCORTING
   ↓
robot resumes
```

Watch:

```bash
ros2 topic echo /museum/escort_state
```

This gives you a very clear **recovery** shot for the video.

---

# 12. Video - Social navigation around another person

The project uses a custom DWB `ProxemicForceCritic`. It evaluates candidate trajectories and penalizes trajectories that enter the personal space of other people, with an anisotropic penalty that gives more space in front of moving people. 

### Video scenario

Place/use the additional human marker on the robot's route:

```text
             PERSON
                ●
                |
TIAGO  ────────→?
```

Then show:

```text
TIAGO approaches person
        ↓
local planner evaluates trajectories
        ↓
direct path becomes undesirable
        ↓
robot chooses alternative trajectory
        ↓
robot passes around person
```

Keep the following visible if possible:

```bash
ros2 topic echo /people
```

The project represents the visitor, guide, and staff member as simulated human markers and converts their positions into a pedestrian stream. 

---

# 13. Video - Arrival

Keep these terminals visible:

### Terminal 3

```bash
ros2 topic echo /museum/navigation_result
```

### Terminal 5

```bash
ros2 topic echo /museum/escort_state
```

Then capture:

```text
Robot reaches final Nav2 waypoint
        ↓
Nav2 SUCCESS
        ↓
visitor is within 2.5 m
        ↓
ARRIVED
```

The important point is that **Nav2 reaching the goal alone is not enough**. The escort supervisor also checks that the visitor is within the arrival radius. 

---

# 14. Final video slide

End with a slide containing:

```text
SEMANTIC MUSEUM GUIDE ROBOT

Demonstrated:

✓ Human–Robot Interaction
✓ Visitor Detection
✓ Speech-to-Text
✓ Language Understanding
✓ Semantic Reasoning
✓ Ambient-Aware Reasoning
✓ Session Memory
✓ Semantic Navigation
✓ Human-Aware / Social Navigation
✓ Visitor Escorting
✓ Escort Recovery
✓ Nav2 Navigation
✓ Task Completion
```

---

# Complete terminal overview

For the actual recording, the easiest setup is:

| Terminal | Purpose                                                    |
| -------- | ---------------------------------------------------------- |
| **1**    | Gazebo + supplied museum + integrated reasoning/navigation |
| **2**    | `/museum/assistant_response`                               |
| **3**    | `/museum/navigation_result`                                |
| **4**    | `/museum/session_state`                                    |
| **5**    | `/museum/escort_state`                                     |
| **6**    | `/museum/ambient_state`                                    |
| **7**    | Speech-to-text                                             |
| **8**    | Send WAV / semantic requests                               |
| **9**    | Ambient experiments                                        |
| **10**   | Session-memory monitoring                                  |

And **every new terminal starts with exactly this host command**:

```bash
cd ~/Desktop/Semantic-Museum-Guide-Robot-with-Ambient-Aware-Reasoning
docker exec -it museum_tiago bash
```

Then, **inside the container**, start with:

```bash
source /root/exchange/exchange/museum_ws/install/setup.bash
```

That should make the whole README much less confusing: **one container, one Gazebo terminal, and every other terminal explicitly reconnects to `museum_tiago` before running a ROS command.**
