# ROS2 Topic Inventory for TIAGo Museum Simulation

## Purpose

This document summarizes the useful ROS 2 topics, nodes, and actions captured from the original TIAGo Gazebo baseline. It connects those real robot interfaces to the architecture of the **Semantic Museum Guide Robot with Ambient-Aware Reasoning** project.

The goal is not to list every topic. Instead, this is an engineering inventory of the interfaces that matter for teleoperation, sensing, mapping, Nav2 navigation, semantic reasoning, future perception, and evaluation.

The inventory is based on the raw captures in `docs/raw/`. Those captures predate the museum semantic nodes and Nav2 launch; statements about what was “not visible” describe that capture, not the current repository.

## Course/Theory Alignment

The project separates the robot system into layers:

- **Geometric/sensor layer:** odometry, laser scans, RGB/depth cameras, point clouds, IMU, sonar, joint states, and TF frames describe where the robot is and what the simulated world looks like geometrically.
- **Semantic layer:** rooms, artworks, crowd level, room status, accessibility, visitor preferences, and speaker roles describe the museum as meaningful entities and relations.
- **Reasoning layer:** the semantic graph and deterministic reasoner transform validated structured requests into intentions, constraints, explanations, and destination choices. Natural-language parsing remains future work.
- **Action layer:** manual teleoperation and manual Nav2 goals are implemented baselines. A future Behavior Executive will connect semantic decisions to navigation.

This supports the project idea of connecting geometric robot data to semantic reasoning. The robot should not rely only on a geometric map or raw coordinates; it should use semantic context to decide where to go and why.

## Key Topics

| Topic | ROS2 message type | Role in the project | Captured baseline usage | Notes |
| --- | --- | --- | --- | --- |
| `/mobile_base_controller/cmd_vel_unstamped` | `geometry_msgs/msg/Twist` | Direct base velocity command for manual movement tests. | Yes | Primary validated command topic for moving TIAGo in the current baseline. Raw info shows 1 publisher and 2 subscribers. |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | Generic velocity command input, likely routed through the velocity/mux stack. | Later | Present with a subscriber but no publisher in the capture. Useful to inspect when adding teleop or Nav2 command routing. |
| `/key_vel` | `geometry_msgs/msg/Twist` | Keyboard teleoperation velocity input candidate. | Later | Present in topic list; may be useful after `teleop_twist_keyboard` is integrated into the workflow. |
| `/joy_vel` | `geometry_msgs/msg/Twist` | Joystick teleoperation velocity input candidate. | No | Present but not part of the current keyboard teleop validation path. |
| `/rviz_joy_vel` | `geometry_msgs/msg/Twist` | RViz joystick velocity input candidate. | No | Useful only if RViz teleop is used. |
| `/tab_vel` | `geometry_msgs/msg/Twist` | Tablet or GUI velocity input candidate. | No | Not needed for the museum baseline. |
| `/assisted_vel` | `geometry_msgs/msg/Twist` | Assisted teleoperation velocity candidate. | Later | Could matter if obstacle-aware assisted teleop is investigated. |
| `/docking_vel` | `geometry_msgs/msg/Twist` | Docking velocity candidate. | No | Not relevant to the museum-guide milestones. |
| `/input_joy/cmd_vel` | `geometry_msgs/msg/Twist` | Joystick command input. | No | Not part of the current baseline. |
| `/mobile_base_controller/cmd_vel_out` | `geometry_msgs/msg/TwistStamped` | Controller output velocity stream. | Later | Useful for debugging what command actually reaches the base controller. |
| `/mobile_base_controller/odom` | `nav_msgs/msg/Odometry` | Wheel/base odometry for localization, mapping, and navigation. | Yes | Main odometry topic in this baseline; `/odom` is not present. Observed around 38 Hz in raw captures. |
| `/ground_truth_odom` | `nav_msgs/msg/Odometry` | Simulation-only ground-truth pose for evaluation/debug. | Later | Useful for comparing estimated navigation behavior against Gazebo truth. Should not be used as the robot's normal localization input. |
| `/scan_raw` | `sensor_msgs/msg/LaserScan` | 2D laser scan for SLAM and obstacle perception. | Later | Main laser topic; `/scan` is not present. Observed around 5 Hz. Candidate input for `slam_toolbox`. |
| `/tf` | `tf2_msgs/msg/TFMessage` | Dynamic transform tree for robot frames and localization. | Yes | Required by robot state, sensor fusion, mapping, and Nav2. Observed around 50 Hz. |
| `/tf_static` | `tf2_msgs/msg/TFMessage` | Static transforms between fixed robot/sensor frames. | Yes | Required for interpreting sensors in the correct coordinate frames. |
| `/joint_states` | `sensor_msgs/msg/JointState` | Joint state stream for robot state publishing and visualization. | Yes | Supports TF generation, RViz visualization, and debugging of the robot model. |
| `/dynamic_joint_states` | `control_msgs/msg/DynamicJointState` | Extended joint/controller state information. | No | Useful mainly for controller debugging. |
| `/head_front_camera/rgb/image_raw` | `sensor_msgs/msg/Image` | RGB stream for future lightweight role-aware vision. | Later | Main candidate topic for guide/staff badge or marker perception. |
| `/head_front_camera/rgb/camera_info` | `sensor_msgs/msg/CameraInfo` | RGB camera calibration metadata. | Later | Needed for camera geometry and any calibrated image processing. |
| `/head_front_camera/depth/image_raw` | `sensor_msgs/msg/Image` | Depth stream for spatial context and future perception. | Later | Useful for estimating person/object distance or validating geometry near exhibits. |
| `/head_front_camera/depth/camera_info` | `sensor_msgs/msg/CameraInfo` | Depth camera calibration metadata. | Later | Needed for depth interpretation. |
| `/head_front_camera/depth/rgb/points` | `sensor_msgs/msg/PointCloud2` | RGB-aligned depth point cloud. | Later | Candidate for future 3D perception or debugging camera/depth alignment. |
| `/filtered_cloud` | `sensor_msgs/msg/PointCloud2` | Filtered point cloud stream. | Later | Useful if obstacle/perception filtering becomes part of the navigation or evaluation pipeline. |
| `/throttle_filtering_points/filtered_points` | `sensor_msgs/msg/PointCloud2` | Point cloud filtering pipeline input/output candidate. | Later | Raw info shows a subscriber but no publisher in the capture. Inspect before use. |
| `/base_imu` | `sensor_msgs/msg/Imu` | Base inertial data for motion sensing and possible localization support. | Later | Present with one publisher. Not needed for manual teleop, but relevant for navigation diagnostics. |
| `/sonar_base` | `sensor_msgs/msg/Range` | Short-range sonar readings around the base. | Later | Present with three publishers. Could support obstacle debugging or safety checks. |
| `/arm_controller/joint_trajectory` | `trajectory_msgs/msg/JointTrajectory` | Arm motion command topic. | No | Not part of the first museum navigation milestones. |
| `/head_controller/joint_trajectory` | `trajectory_msgs/msg/JointTrajectory` | Head motion command topic. | Later | Could be used later to orient the head/camera toward visitors or exhibits. |
| `/gripper_controller/joint_trajectory` | `trajectory_msgs/msg/JointTrajectory` | Gripper motion command topic. | No | Not required for the museum guide scenario. |
| `/torso_controller/joint_trajectory` | `trajectory_msgs/msg/JointTrajectory` | Torso motion command topic. | No | Not required for current milestones. |
| `/robot_description` | `std_msgs/msg/String` | Robot URDF description. | Yes | Supports robot model visualization and state publishing. |
| `/robot_description_semantic` | `std_msgs/msg/String` | Semantic robot description for MoveIt-related components. | No | Present because MoveIt components are visible, but not part of museum semantic reasoning. |
| `/performance_metrics` | `gazebo_msgs/msg/PerformanceMetrics` | Gazebo runtime performance metrics. | Later | Useful for debugging simulation load on limited hardware. |
| `/diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | System diagnostics. | Later | Useful for debugging controllers and runtime health. |

## Nodes and Actions Summary

Visible nodes in the current baseline include simulation, control, sensing, TF, and MoveIt-related components:

- Gazebo and simulation control: `/gazebo`, `/gazebo_ros2_control`, `/gazebo_ros_odometry`
- Base and sensor nodes: `/mobile_base_controller`, `/base_laser`, `/base_imu`, `/base_sonar_01_gazebo_ros_range`, `/base_sonar_02_gazebo_ros_range`, `/base_sonar_03_gazebo_ros_range`
- Robot state and transforms: `/robot_state_publisher`, `/joint_state_broadcaster`, transform listener nodes
- Command routing: `/twist_mux`, `/twist_mux/add_analyzer_node`, `/joystick_relay`
- Joint controllers: `/arm_controller`, `/head_controller`, `/gripper_controller`, `/torso_controller`, `/controller_manager`
- Motion/manipulation support visible in the baseline: `/move_group`, `/moveit_simple_controller_manager`, `/play_motion2_executor`, `/play_motion2_mgr`

Visible actions include:

- `/arm_controller/follow_joint_trajectory`
- `/gripper_controller/follow_joint_trajectory`
- `/head_controller/follow_joint_trajectory`
- `/torso_controller/follow_joint_trajectory`
- `/execute_trajectory`
- `/move_action`
- `/play_motion2`
- `/play_motion2/raw`
- joystick priority/turbo actions such as `/joy_priority_action`

Nav2 actions such as `/navigate_to_pose` are absent from this raw capture because Nav2 was not running when it was recorded. The current repository includes a known-map Nav2 launch and a helper client for that action.

## Museum Package Interfaces Added Later

| Interface | Type | Current role |
| --- | --- | --- |
| `/museum/ambient_state` | `std_msgs/msg/String` containing validated JSON fields | Scripted room crowd/noise/status updates consumed into process-local semantic state. |
| `/museum/user_request` | `std_msgs/msg/String` containing structured JSON | Manual or scripted input to the deterministic reasoner; not natural language. |
| `/museum/assistant_response` | `std_msgs/msg/String` containing structured JSON | Reasoning result consumed by the filtered semantic-navigation/escort node. |
| `/museum/session_state` | `std_msgs/msg/String` containing JSON | One in-memory session for the static simulated visitor. |
| `/museum/visitor_observation` | `std_msgs/msg/String` containing JSON | Gazebo-ground-truth visitor presence and planar distance without simulator model names. |
| `/museum/navigation_result` | `std_msgs/msg/String` containing JSON | Correlated low-level Nav2 acceptance and terminal result. |
| `/museum/escort_state` | `std_msgs/msg/String` containing JSON | Correlated `escorting`, `waiting`, `lost`, or `arrived` state for one task. |
| `/map` | `nav_msgs/msg/OccupancyGrid` | SLAM output or saved-map server output. |
| `/amcl_pose` | `geometry_msgs/msg/PoseWithCovarianceStamped` | Known-map localization and semantic pose capture. |
| `/navigate_to_pose` | `nav2_msgs/action/NavigateToPose` | Manual tools or the filtered semantic-navigation node; only that node owns escort pause/resume goals. |

## Mapping to Project Architecture

| Project module | ROS2 interfaces | Use in the project |
| --- | --- | --- |
| Motion primitive / teleop | `/mobile_base_controller/cmd_vel_unstamped`, `/cmd_vel`, `/key_vel`, `/mobile_base_controller/cmd_vel_out` | Validate TIAGo movement and debug the command path. |
| Geometric map | `/scan_raw`, `/mobile_base_controller/odom`, `/tf`, `/tf_static`, `/map`, `/amcl_pose` | Build and localize against the saved museum map. |
| Semantic map | No direct TIAGo topic; stored in project configuration and semantic graph nodes. | Represents rooms, artworks, navigation poses, styles, constraints, and relations. |
| Ambient sensors | `/museum/ambient_state` | Provides scripted dynamic semantic state such as crowd level, noise, and closures. |
| Structured reasoning | `/museum/user_request`, `/museum/assistant_response` | Produces deterministic recommendations and prepared navigation skills. |
| Simulated escort | `/museum/session_state`, `/museum/visitor_observation`, `/museum/escort_state`, `/museum/navigation_result` | Supervises one static visitor with Gazebo ground truth; not real tracking or social navigation. |
| Role-aware vision | `/head_front_camera/rgb/image_raw`, `/head_front_camera/depth/image_raw`, camera info topics, point clouds | Future lightweight detection of guide/staff badge or marker cues. |
| Nav2 baseline | `/navigate_to_pose` plus controller command routing | Executes manual goals and filtered semantic goals while preserving DWB unchanged. |
| Evaluation/debug | `/ground_truth_odom`, `/performance_metrics`, `/diagnostics`, `/joint_states`, `/tf` | Compare estimated behavior to simulation truth and debug controller/simulation health. |

## Current Engineering Notes

- **SLAM:** `museum_slam.launch.py` remaps the SLAM node's `scan` input to `/scan_raw`. Odometry and transforms remain central diagnostics.
- **Known map:** `maps/museum_map.yaml` and `.pgm` exist and are used by `museum_navigation.launch.py`.
- **Navigation:** Nav2/AMCL/DWB form the current baseline. The accepted Phase 3 semantic decision path is connected to `/navigate_to_pose` through `semantic_navigation_node`.
- **Localization:** `/mobile_base_controller/odom` and TF are central to localization and navigation diagnostics. The absence of plain `/odom` should be reflected in launch/config remappings.
- **Semantic reasoning:** Museum concepts map to poses in YAML, but poses need calibration. Raw coordinates must never come from user language or an LLM.
- **Ambient-aware behavior:** Scripted ambient updates influence subsequent recommendations. Active-task adaptation is not implemented.
- **Identity:** The simulation adapter translates `visitor_marker` to public `visitor_1`/`session_1` identifiers and keeps Gazebo model names out of downstream JSON.
- **Role-aware vision:** The head RGB and depth topics provide the future input path for lightweight guide/staff badge recognition. This should remain role/context recognition, not personal identity recognition.
- **Evaluation/debug:** `/ground_truth_odom` can support simulation-only evaluation by comparing planned or estimated robot movement with Gazebo truth. It should not be used as a normal navigation dependency.
