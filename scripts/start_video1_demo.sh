#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="museum_tiago"
STATE_DIR="/tmp/tiago_video1_demo_${UID}"
ROS_SETUP="source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash && source /root/exchange/exchange/museum_ws/install/setup.bash"
BUILD_SETUP="source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash"
GOAL_X="0.0"
GOAL_Y="16.0"
GOAL_YAW="1.5708"
ACCEPTED_NAV2_PARAMS="/root/exchange/exchange/museum_ws/src/museum_assistant/config/nav2_supplied_anisotropic.yaml"
RVIZ_CONFIG="/root/exchange/exchange/rviz/video1_social_navigation.rviz"
MOVE_GUIDE="true"
RVIZ_AVAILABLE="true"

if [[ "${1:-}" == "--static-guide" ]]; then
  MOVE_GUIDE="false"
  shift
elif [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: $0 [--static-guide]"
  echo "Default: nine static people and one slowly moving guide."
  echo "Fallback: --static-guide keeps all ten people stationary."
  exit 0
fi
if (($#)); then
  echo "Unknown argument: $1" >&2
  echo "Usage: $0 [--static-guide]" >&2
  exit 2
fi

command -v docker >/dev/null || { echo "docker is required." >&2; exit 1; }

if command -v gnome-terminal >/dev/null; then
  TERMINAL="gnome-terminal"
elif command -v x-terminal-emulator >/dev/null; then
  TERMINAL="x-terminal-emulator"
else
  echo "No supported terminal found." >&2
  exit 1
fi

container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null || true)" == "true" ]]
}

if ! container_running; then
  echo "${CONTAINER} is not running." >&2
  echo "Start ./start_museum_tiago.sh in another terminal and leave it open." >&2
  exit 1
fi

mkdir -p "${STATE_DIR}"
for pid_file in "${STATE_DIR}"/*.pid; do
  [[ -e "${pid_file}" ]] || continue
  pid="$(<"${pid_file}")"
  if [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null; then
    echo "A Video 1 helper is already running. Use scripts/stop_video1_demo.sh first." >&2
    exit 1
  fi
  rm -f "${pid_file}"
done

open_terminal() {
  local title="$1" process_name="$2" command="$3"
  local pid_file="${STATE_DIR}/${process_name}.pid" wrapped
  printf -v wrapped 'printf "%%s\n" "$$" > %q; exec %s' "${pid_file}" "${command}"
  if [[ "${TERMINAL}" == "gnome-terminal" ]]; then
    gnome-terminal --title="${title}" -- bash -lc "${wrapped}"
  else
    x-terminal-emulator -T "${title}" -e bash -lc "${wrapped}"
  fi
}

start_background() {
  local process_name="$1" command="$2"
  local pid_file="${STATE_DIR}/${process_name}.pid"
  bash -lc "exec ${command}" >"${STATE_DIR}/${process_name}.log" 2>&1 &
  printf '%s\n' "$!" >"${pid_file}"
}

ros_exec() {
  docker exec "${CONTAINER}" bash -lc "${ROS_SETUP} && $1"
}

set_top_down_gazebo_camera() {
  local topics attempt
  local camera_topic="/gazebo/default/user_camera/joy_pose"
  local camera_pose
  camera_pose='position { x: 0 y: 8 z: 38 } orientation { x: -0.5 y: 0.5 z: 0.5 w: 0.5 }'
  for attempt in {1..30}; do
    topics="$(docker exec "${CONTAINER}" gz topic -l 2>/dev/null || true)"
    if grep -Fxq "${camera_topic}" <<<"${topics}"; then
      docker exec "${CONTAINER}" gz topic -p "${camera_topic}" \
        -m "${camera_pose}" >/dev/null 2>&1
      return 0
    fi
    sleep 1
  done
  return 1
}

hide_gazebo_lidar_visual() {
  local topics attempt
  local scan_topic="/gazebo/default/tiago/base_footprint/base_laser/scan"
  local visual_topic="/gazebo/default/visual"
  local visual_message
  visual_message="name: 'tiago::base_footprint::base_laser_GUIONLY_laser_vis' parent_name: 'tiago::base_footprint' visible: false"
  for attempt in {1..60}; do
    topics="$(docker exec "${CONTAINER}" gz topic -l 2>/dev/null || true)"
    if grep -Fxq "${scan_topic}" <<<"${topics}"; then
      # This targets Gazebo's _GUIONLY_ LaserVisual. It does not disable the
      # sensor or alter /scan_raw, and only removes the blue ray overlay.
      for _ in 1 2 3; do
        docker exec "${CONTAINER}" gz topic -p "${visual_topic}" \
          -m "${visual_message}" >/dev/null 2>&1 || return 1
        sleep 1
      done
      return 0
    fi
    sleep 1
  done
  return 1
}

docker exec "${CONTAINER}" test -d /root/exchange/exchange/museum_ws || {
  echo "${CONTAINER} does not contain the expected /root/exchange mount." >&2
  exit 1
}

existing_topics="$(ros_exec "ros2 topic list" 2>/dev/null || true)"
existing_actions="$(ros_exec "ros2 action list" 2>/dev/null || true)"
existing_nodes="$(ros_exec "ros2 node list" 2>/dev/null || true)"
if grep -Fxq "/gazebo/model_states" <<<"${existing_topics}" \
  || grep -Fxq "/navigate_to_pose" <<<"${existing_actions}" \
  || grep -Eq '^/(gazebo|controller_server|bt_navigator|demo_crowd_motion|demo_static_people)$' <<<"${existing_nodes}"; then
  echo "An existing Gazebo/Nav2/Video1 runtime is already active." >&2
  echo "Run ./scripts/stop_video1_demo.sh, close the old simulation, then start again." >&2
  exit 1
fi

echo "Building museum_assistant and museum_social_critic..."
docker exec "${CONTAINER}" bash -lc \
  "${BUILD_SETUP} && cd /root/exchange/exchange/museum_ws && colcon build --symlink-install --packages-select museum_assistant museum_social_critic"

# Use the accepted anisotropic profile directly and unchanged. Video 1 sends
# one NavigateToPose goal; DWB and ProxemicForce choose the local trajectory.
echo "Using accepted social-navigation profile: ${ACCEPTED_NAV2_PARAMS}"
docker exec "${CONTAINER}" test -f "${ACCEPTED_NAV2_PARAMS}" || {
  echo "Accepted Nav2 profile is missing inside ${CONTAINER}." >&2
  exit 1
}
if ! docker exec "${CONTAINER}" test -f "${RVIZ_CONFIG}"; then
  echo "WARNING: Video 1 RViz config is missing; navigation will continue." >&2
  RVIZ_AVAILABLE="false"
fi

SIMULATION_REMOTE="${ROS_SETUP} && exec ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py gzclient:=True publish_people:=True use_scripted_visitor:=False use_engagement:=False use_language:=False use_speech:=False nav2_params_file:=${ACCEPTED_NAV2_PARAMS}"
printf -v simulation_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${SIMULATION_REMOTE}"
open_terminal "TIAGO - SIMULATION" "simulation" "${simulation_command}"

gazebo_ready() {
  local services
  services="$(ros_exec "ros2 service list" 2>/dev/null)" || return 1
  grep -Fxq "/gazebo/set_entity_state" <<<"${services}" \
    && grep -Fxq "/spawn_entity" <<<"${services}" \
    && grep -Fxq "/delete_entity" <<<"${services}"
}

echo "Waiting for Gazebo services..."
deadline=$((SECONDS + 180))
until gazebo_ready; do
  if ((SECONDS >= deadline)); then
    echo "Timed out waiting for Gazebo services. Check TIAGO - SIMULATION." >&2
    exit 1
  fi
  sleep 2
done

echo "Gazebo READY. Opening Video 1 visualization, monitor and control."

if set_top_down_gazebo_camera; then
  echo "Gazebo camera set to the Video 1 bird's-eye view."
else
  echo "WARNING: Gazebo camera topic was unavailable; set the view manually." >&2
fi
if hide_gazebo_lidar_visual; then
  echo "Gazebo LiDAR ray overlay hidden; the /scan_raw sensor remains active."
else
  echo "WARNING: Gazebo LiDAR visual could not be hidden." >&2
fi

GUIDE_ARGUMENT=""
PEOPLE_MODE="MOVING GUIDE"
if [[ "${MOVE_GUIDE}" == "true" ]]; then
  GUIDE_ARGUMENT="--move-guide"
else
  PEOPLE_MODE="STATIC FALLBACK"
fi
PEOPLE_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_static_people.py ${GUIDE_ARGUMENT} --ros-args -p use_sim_time:=true"
printf -v people_command 'docker exec -i %q bash -lc %q' "${CONTAINER}" "${PEOPLE_REMOTE}"
start_background "crowd" "${people_command}"

VISUALIZER_REMOTE="${ROS_SETUP} && exec ros2 run museum_assistant social_visualization_node --ros-args -p use_sim_time:=true"
printf -v visualizer_command 'docker exec -i %q bash -lc %q' "${CONTAINER}" "${VISUALIZER_REMOTE}"
start_background "visualizer" "${visualizer_command}"

RVIZ_REMOTE="${ROS_SETUP} && exec rviz2 -d ${RVIZ_CONFIG}"
printf -v rviz_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${RVIZ_REMOTE}"
if [[ "${RVIZ_AVAILABLE}" == "true" ]]; then
  if ! open_terminal "TIAGO - RVIZ SOCIAL NAVIGATION" "rviz" "${rviz_command}"; then
    echo "WARNING: RViz did not start; navigation will continue." >&2
  fi
fi

MONITOR_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_social_monitor.py"
printf -v monitor_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${MONITOR_REMOTE}"
open_terminal "TIAGO - SOCIAL MONITOR" "monitor" "${monitor_command}"

read -r -d '' CONTROL_TEXT <<EOF || true
clear
printf '%s\n' \
'============================================' \
' TIAGO MUSEUM GUIDE - VIDEO 1 CONTROL' \
'============================================' \
'' \
'ONLY NAVIGATION GOAL:' \
'  north_gallery = (0.0, 16.0)' \
'' \
'NO intermediate waypoint.' \
'Local DWB + ProxemicForce chooses the deviation.' \
'' \
'Waiting for Nav2 + 10 people...'

while true; do
  controller="\$(ros2 lifecycle get /controller_server 2>/dev/null || true)"
  navigator="\$(ros2 lifecycle get /bt_navigator 2>/dev/null || true)"
  snapshot="\$(timeout 5 ros2 topic echo /people --once 2>/dev/null || true)"
  people_count="\$(grep -c 'identifier:' <<<"\$snapshot" || true)"
  visitor_present="\$(ros2 topic echo /gazebo/model_states --once --field name 2>/dev/null | grep -c visitor_marker || true)"
  nodes="\$(ros2 node list 2>/dev/null || true)"
  topics="\$(ros2 topic list 2>/dev/null || true)"
  rviz_ready="\$(grep -Ec '^/rviz(2)?(_[0-9]+)?$' <<<"\$nodes" || true)"
  visualizer_ready="\$(grep -c '^/social_visualization_node$' <<<"\$nodes" || true)"
  markers_ready="\$(grep -c '^/museum/social_markers$' <<<"\$topics" || true)"

  clear
  printf '%s\n' \
  '============================================' \
  ' TIAGO MUSEUM GUIDE - VIDEO 1 CONTROL' \
  '============================================' \
  "controller_server: \${controller:-waiting}" \
  "bt_navigator:      \${navigator:-waiting}" \
  "people on /people: \$people_count / 10" \
  "near-spawn visitor removed: \$([[ \$visitor_present -eq 0 ]] && echo YES || echo waiting)" \
  "RViz process:       \$([[ \$rviz_ready -gt 0 ]] && echo READY || echo optional/waiting)" \
  "social visualizer:  \$([[ \$visualizer_ready -gt 0 ]] && echo READY || echo optional/waiting)" \
  "social marker topic:\$([[ \$markers_ready -gt 0 ]] && echo ' READY' || echo ' optional/waiting')" \
  '' \
  'Single goal only: north_gallery (0,16)'

  if [[ "\$controller" == "active [3]" \
        && "\$navigator" == "active [3]" \
        && "\$people_count" -eq 10 \
        && "\$visitor_present" -eq 0 ]]; then
    break
  fi
  sleep 2
done

clear
printf '%s\n' \
'============================================' \
' VIDEO 1 READY - SINGLE GOAL' \
'============================================' \
'Nav2: ACTIVE' \
'People: 10 / 10' \
'Near-spawn visitor: REMOVED' \
'People mode: ${PEOPLE_MODE}' \
'RViz + social markers: checked (visualization is non-blocking)' \
'Goal: north_gallery (0.0, 16.0)' \
'Waypoints: NONE' \
'============================================'
for n in 8 7 6 5 4 3 2 1; do
  printf '\rNavigation starts in %2d s ' "\$n"
  sleep 1
done
printf '\nSINGLE NAVIGATION GOAL SENT -> NORTH GALLERY\n'
exec ros2 run museum_assistant send_nav_goal --x ${GOAL_X} --y ${GOAL_Y} --yaw ${GOAL_YAW}
EOF
CONTROL_REMOTE="${ROS_SETUP} && ${CONTROL_TEXT}"
printf -v control_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${CONTROL_REMOTE}"
open_terminal "TIAGO - VIDEO CONTROL" "control" "${control_command}"

echo "Video 1 single-goal demo started."
echo "People mode: ${PEOPLE_MODE}. Use --static-guide for the validated fallback."
echo "Only north_gallery (0,16) is sent. No waypoint route exists in this script."
echo "visitor_marker next to spawn is deleted before navigation starts."
echo "Stop with: ./scripts/stop_video1_demo.sh"
