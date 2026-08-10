# Sensor-based interaction availability

## 1. Motivation

The museum demo needs a sensor-grounded interaction start without granting
the simulator hidden knowledge to the engagement decision. The system
therefore estimates **interaction availability** from multimodal visual,
spatial, motion, and temporal cues. It does not claim to infer intention.

## 2. Human visual assets

`visitor_marker`, `guide_marker`, and `staff_marker` retain their model names,
world poses, public IDs, and scripted behavior. Their cylinder-and-sphere
visuals are replaced by the posed `person_standing` mesh from the OSRF Gazebo
model database. The model metadata credits Marina Kollmitz and states that it
was created with MakeHuman. The database license is CC BY 3.0; the exact
attribution and license are installed beside the asset under
`worlds/supplied_museum/humans/person_standing/`.

The human mesh is visual only. The old torso dimensions are retained as a
separate cylinder (`radius=0.16 m`, `length=0.75 m`) for simple laser-visible
collision geometry; the mesh itself is never used for collision. Blue and red
badges distinguish guide and staff without introducing identity recognition.

## 3. RGB person detector

`person_detector.py` runs the FP32 NanoDet model published by the OpenCV Model
Zoo with OpenCV DNN. The 3.8 MB ONNX weight is pretrained on COCO and licensed
under Apache-2.0; `models/README.md` records its URL, license, and SHA-256.
No training or fine-tuning was performed. Only COCO class `person` is used.

The threshold selected from the real Gazebo probe is `0.35`. At 640×480, the
80-frame probe produced 20/20 detections for frontal-near, 20/20 for
frontal-far, 20/20 lateral detections, and 0/20 detections with no person.
Mean CPU inference latency was 189.1 ms and p95 was 211.6 ms with OpenCV 4.5.4.
The camera delivered 640×480 BGR frames at approximately 21–30 FPS; runtime
inference is intentionally limited to 5 Hz.

## 4. LiDAR proximity

`engagement_node` reads `/scan_raw` and chooses the closest finite point in a
front cone of ±35 degrees. Values outside the sensor range or below 0.35 m are
ignored. A visual detection alone cannot engage, and a LiDAR return alone
cannot engage. The maximum engagement distance is 2.0 m.

## 5. Temporal engagement state machine

The pure deterministic state machine has exactly these states:

```text
NO_PERSON -> PASSING -> POTENTIAL_INTERACTION -> ENGAGED
                                                   |
                                                   v
                                             DISENGAGING
                                                   |
                                                   v
                                              NO_PERSON
```

A detection must be inside the central 70% of the image and agree with a
near frontal LiDAR return. `POTENTIAL_INTERACTION` requires 1.0 s dwell;
`ENGAGED` requires 2.5 s dwell and radial speed at or below 0.25 m/s. Loss of
the cues after engagement enters `DISENGAGING` and reaches `NO_PERSON` after
1.5 s unless the cues return.

The engagement node subscribes only to:

- `/head_front_camera/rgb/image_raw`
- `/scan_raw`
- ROS time

It has no Gazebo message import, model name, pose, or ground-truth topic.

## 6. Session activation

Historical behavior remains the default. With `require_engagement:=False`,
`visitor_session_node` activates from the existing simulated model presence.
With `require_engagement:=True`, it activates the generic `visitor_1` /
`session_1` only after `/museum/engagement_state` reports `engaged`; simulator
model presence is not part of that activation decision.

Run the supplied full stack in the opt-in mode with:

```bash
ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py \
  gzclient:=False use_engagement:=True require_engagement:=True
```

Add `publish_debug_image:=True` to publish the bounding box, confidence,
state, and distance on `/museum/engagement_debug_image` for RViz or
`rqt_image_view`. The node never opens an OpenCV window.

## 7. Evaluation

Unit tests cover preprocessing, class filtering, candidate selection, all
specified fusion transitions, invalid LiDAR, jitter, and repeatability. The
ROS-light test uses a fake detector result plus a synthetic `LaserScan` and
checks both public topics. `scripts/final_benchmark.py offline` exports the
seven bounded cases E1–E7 to `benchmarks/raw/engagement.csv`; this is a
bounded engagement-state benchmark, not human-intention accuracy.

The real sensor acceptance observed:

- EMPTY: repeated `NO_PERSON`, no session;
- PASSING: `PASSING` then `NO_PERSON`, never `ENGAGED`;
- INTERACTION: `PASSING -> POTENTIAL_INTERACTION -> ENGAGED` in 2.57 s,
  followed by `session_1` becoming `ACTIVE`.

## 8. Limitations

Evaluation is simulation-specific. There is no identity, face, emotion, gaze,
pose, or true-intention recognition. The detector treats visitor, guide, and
staff only as `person`. Vision is used for interaction initiation; after
activation, escort visitor monitoring remains simulation-assisted through the
existing Gazebo observation adapter. EscortSupervisor and the downstream
reasoning/navigation pipeline are unchanged.
