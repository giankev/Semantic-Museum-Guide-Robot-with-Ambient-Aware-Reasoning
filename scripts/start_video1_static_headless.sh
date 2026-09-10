#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="museum_tiago"
STATE_DIR="/tmp/tiago_video1_static_headless_${UID}"
ROS_SETUP="source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash && source /root/exchange/exchange/museum_ws/install/setup.bash"
BUILD_SETUP="source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash"
GOAL_X="0.0"
GOAL_Y="16.0"
GOAL_YAW="1.5708"

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
command -v gnome-terminal >/dev/null || { echo "gnome-terminal is required" >&2; exit 1; }

container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null || true)" == "true" ]]
}

if ! container_running; then
  echo "${CONTAINER} is not running." >&2
  echo "Run ./start_museum_tiago.sh first and leave that terminal open." >&2
  exit 1
fi

mkdir -p "${STATE_DIR}"

open_terminal() {
  local title="$1"
  local name="$2"
  local command="$3"
  local pid_file="${STATE_DIR}/${name}.pid"
  local wrapped
  printf -v wrapped 'printf "%%s\n" "$$" > %q; exec %s' "${pid_file}" "${command}"
  gnome-terminal --title="${title}" -- bash -lc "${wrapped}"
}

ros_exec() {
  docker exec "${CONTAINER}" bash -lc "${ROS_SETUP} && $1"
}

existing_topics="$(ros_exec "ros2 topic list" 2>/dev/null || true)"
existing_actions="$(ros_exec "ros2 action list" 2>/dev/null || true)"
if grep -Fxq "/gazebo/model_states" <<<"${existing_topics}" || grep -Fxq "/navigate_to_pose" <<<"${existing_actions}"; then
  echo "An old Gazebo/Nav2 runtime is still active." >&2
  echo "Close it first, then rerun this script." >&2
  exit 1
fi

echo "Building packages..."
docker exec "${CONTAINER}" bash -lc \
  "${BUILD_SETUP} && cd /root/exchange/exchange/museum_ws && colcon build --symlink-install --packages-select museum_assistant museum_social_critic"

SIM_REMOTE="${ROS_SETUP} && exec ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py gzclient:=False publish_people:=True use_engagement:=False use_language:=False use_speech:=False nav2_params_file:=/root/exchange/exchange/museum_ws/src/museum_assistant/config/nav2_supplied_anisotropic.yaml"
printf -v sim_cmd 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${SIM_REMOTE}"
open_terminal "TIAGO - HEADLESS SIM" "simulation" "${sim_cmd}"

nav2_ready() {
  local controller navigator
  controller="$(ros_exec "ros2 lifecycle get /controller_server" 2>/dev/null || true)"
  navigator="$(ros_exec "ros2 lifecycle get /bt_navigator" 2>/dev/null || true)"
  grep -Eq '^active \[3\]$' <<<"${controller}" && grep -Eq '^active \[3\]$' <<<"${navigator}"
}

gazebo_ready() {
  ros_exec "ros2 service list" 2>/dev/null | grep -Fxq "/gazebo/set_entity_state"
}

echo "Waiting for headless Gazebo + Nav2..."
deadline=$((SECONDS + 300))
until gazebo_ready && nav2_ready; do
  if (( SECONDS >= deadline )); then
    echo "Timed out waiting for headless simulation." >&2
    exit 1
  fi
  sleep 2
done

STATIC_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_static_people.py"
printf -v static_cmd 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${STATIC_REMOTE}"
open_terminal "TIAGO - STATIC PEOPLE" "static_people" "${static_cmd}"

MONITOR_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_monitor.py"
printf -v monitor_cmd 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${MONITOR_REMOTE}"
open_terminal "TIAGO - MONITOR" "monitor" "${monitor_cmd}"

echo "Waiting for all six static pedestrians on /people..."
deadline=$((SECONDS + 90))
while true; do
  sample="$(ros_exec "timeout 5 ros2 topic echo /people --once" 2>/dev/null || true)"
  count="$(grep -c 'identifier:' <<<"${sample}" || true)"
  if [[ "${count}" -eq 6 ]]; then
    break
  fi
  if (( SECONDS >= deadline )); then
    echo "Timed out waiting for six people." >&2
    exit 1
  fi
  sleep 2
done

echo "STATIC HEADLESS READY"
echo "Six people are published. Sending north_gallery goal in 5 seconds..."
sleep 5

GOAL_REMOTE="${ROS_SETUP} && exec ros2 run museum_assistant send_nav_goal --x ${GOAL_X} --y ${GOAL_Y} --yaw ${GOAL_YAW}"
printf -v goal_cmd 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${GOAL_REMOTE}"
open_terminal "TIAGO - STATIC NAV GOAL" "goal" "${goal_cmd}"

echo "Goal sent to (${GOAL_X}, ${GOAL_Y})."
echo "Headless mode is running: no Gazebo GUI should be open."
echo "Use the monitor and navigation terminal to check stability first."
