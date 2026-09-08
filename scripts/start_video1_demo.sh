#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="museum_tiago"
STATE_DIR="/tmp/tiago_video1_demo_${UID}"
ROS_SETUP="source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash && source /root/exchange/exchange/museum_ws/install/setup.bash"
BUILD_SETUP="source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash"

# Validated north-gallery candidate from supplied_museum_routes.yaml.
GOAL_X="0.0"
GOAL_Y="16.0"
GOAL_YAW="1.5708"
AUTO_START_DELAY="12"

command -v docker >/dev/null || {
  echo "docker is required." >&2
  exit 1
}

if command -v gnome-terminal >/dev/null; then
  TERMINAL="gnome-terminal"
elif command -v x-terminal-emulator >/dev/null; then
  TERMINAL="x-terminal-emulator"
else
  echo "No supported terminal found (gnome-terminal or x-terminal-emulator)." >&2
  exit 1
fi

container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null || true)" == "true" ]]
}

if ! container_running; then
  echo "${CONTAINER} is not running." >&2
  echo "Start ./start_museum_tiago.sh in another terminal and leave it open, then rerun this script." >&2
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
  local title="$1"
  local process_name="$2"
  local command="$3"
  local pid_file="${STATE_DIR}/${process_name}.pid"
  local wrapped
  printf -v wrapped 'printf "%%s\n" "$$" > %q; exec %s' "${pid_file}" "${command}"
  if [[ "${TERMINAL}" == "gnome-terminal" ]]; then
    gnome-terminal --title="${title}" -- bash -lc "${wrapped}"
  else
    x-terminal-emulator -T "${title}" -e bash -lc "${wrapped}"
  fi
}

ros_exec() {
  docker exec "${CONTAINER}" bash -lc "${ROS_SETUP} && $1"
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
  || grep -Eq '^/(gazebo|controller_server|bt_navigator|demo_crowd_motion)$' <<<"${existing_nodes}"; then
  echo "An existing Gazebo/Nav2/Video1 runtime is already active." >&2
  echo "Run ./scripts/stop_video1_demo.sh, close the old simulation, then start again." >&2
  exit 1
fi

echo "Building museum_assistant and museum_social_critic..."
docker exec "${CONTAINER}" bash -lc \
  "${BUILD_SETUP} && cd /root/exchange/exchange/museum_ws && colcon build --symlink-install --packages-select museum_assistant museum_social_critic"

SIMULATION_REMOTE="${ROS_SETUP} && exec ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py gzclient:=True publish_people:=True use_engagement:=False use_language:=False use_speech:=False nav2_params_file:=/root/exchange/exchange/museum_ws/src/museum_assistant/config/nav2_supplied_anisotropic.yaml"
printf -v simulation_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${SIMULATION_REMOTE}"
open_terminal "TIAGO - SIMULATION" "simulation" "${simulation_command}"

gazebo_ready() {
  local services
  services="$(ros_exec "ros2 service list" 2>/dev/null)" || return 1
  grep -Fxq "/gazebo/set_entity_state" <<<"${services}" \
    && grep -Fxq "/spawn_entity" <<<"${services}"
}

nav2_ready() {
  local actions controller navigator
  actions="$(ros_exec "ros2 action list" 2>/dev/null)" || return 1
  grep -Fxq "/navigate_to_pose" <<<"${actions}" || return 1
  controller="$(ros_exec "ros2 lifecycle get /controller_server" 2>/dev/null)" || return 1
  navigator="$(ros_exec "ros2 lifecycle get /bt_navigator" 2>/dev/null)" || return 1
  grep -Eq '^active \[3\]$' <<<"${controller}" \
    && grep -Eq '^active \[3\]$' <<<"${navigator}"
}

robot_at_demo_start() {
  local position x y
  position="$(ros_exec "timeout 5 ros2 topic echo /museum/ground_truth_odom --once --field pose.pose.position" 2>/dev/null)" || return 1
  x="$(awk '$1 == "x:" {print $2; exit}' <<<"${position}")"
  y="$(awk '$1 == "y:" {print $2; exit}' <<<"${position}")"
  awk -v x="${x}" -v y="${y}" 'BEGIN {exit !(x != "" && y != "" && sqrt(x*x+y*y) <= 0.50)}'
}

echo "Waiting for Gazebo and exact Nav2 active state..."
deadline=$((SECONDS + 300))
until gazebo_ready && nav2_ready; do
  if ((SECONDS >= deadline)); then
    echo "Timed out waiting for Gazebo/Nav2." >&2
    exit 1
  fi
  sleep 2
done

echo "Nav2 is ACTIVE. The play_motion2 /robot_description_semantic warning is not used by this base-navigation demo."

if ! robot_at_demo_start; then
  echo "TIAGo is not near the expected start (0,0)." >&2
  exit 1
fi

CROWD_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_crowd_motion.py --seed 42 --count 6 --ros-args -p use_sim_time:=true"
printf -v crowd_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${CROWD_REMOTE}"
open_terminal "TIAGO - CROWD" "crowd" "${crowd_command}"

MONITOR_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_monitor.py"
printf -v monitor_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${MONITOR_REMOTE}"
open_terminal "TIAGO - MONITOR" "monitor" "${monitor_command}"

# Do not gate navigation on fragile /people parsing.  The crowd is given a
# short deterministic startup window, then a normal Nav2 goal is sent
# automatically.  The robot takes long enough to reach y>10 that all six
# pedestrians will already be walking in the north gallery when it arrives.
read -r -d '' CONTROL_TEXT <<EOF || true
clear
printf '%s\n' \
'============================================' \
' TIAGO MUSEUM GUIDE - VIDEO 1 AUTO START' \
'============================================' \
'' \
'Nav2: ACTIVE' \
'Social critic: ANISOTROPIC' \
'People requested: 6' \
'Crowd location: NORTH GALLERY' \
'Goal: NORTH GALLERY (0.0, 16.0)' \
'' \
'TIAGo will start automatically.' \
'No ENTER is required.' \
'============================================'
for n in 12 11 10 9 8 7 6 5 4 3 2 1; do
  printf '\rNavigation starts in %2d s ' "\$n"
  sleep 1
done
printf '\nNAVIGATION GOAL SENT -> NORTH GALLERY\n'
exec ros2 run museum_assistant send_nav_goal --x ${GOAL_X} --y ${GOAL_Y} --yaw ${GOAL_YAW}
EOF
CONTROL_REMOTE="${ROS_SETUP} && ${CONTROL_TEXT}"
printf -v control_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${CONTROL_REMOTE}"
open_terminal "TIAGO - VIDEO CONTROL" "control" "${control_command}"

echo "Video 1 started. No further input is needed."
echo "TIAGo will automatically navigate to north_gallery (0,16) after ${AUTO_START_DELAY}s."
echo "The six NPCs walk continuously in the north room while TIAGo approaches."
echo "Stop with: ./scripts/stop_video1_demo.sh"
