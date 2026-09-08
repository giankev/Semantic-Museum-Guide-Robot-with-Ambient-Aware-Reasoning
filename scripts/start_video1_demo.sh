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
AUTO_START_DELAY="8"
DEMO_NAV2_PARAMS="/tmp/nav2_video1_static.yaml"

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
  || grep -Eq '^/(gazebo|controller_server|bt_navigator|demo_crowd_motion|demo_static_people)$' <<<"${existing_nodes}"; then
  echo "An existing Gazebo/Nav2/Video1 runtime is already active." >&2
  echo "Run ./scripts/stop_video1_demo.sh, close the old simulation, then start again." >&2
  exit 1
fi

echo "Building museum_assistant and museum_social_critic..."
docker exec "${CONTAINER}" bash -lc \
  "${BUILD_SETUP} && cd /root/exchange/exchange/museum_ws && colcon build --symlink-install --packages-select museum_assistant museum_social_critic"

echo "Preparing Video 1 social-navigation profile (3.0 m comfort target)..."
docker exec "${CONTAINER}" bash -lc "
  cp /root/exchange/exchange/museum_ws/src/museum_assistant/config/nav2_supplied_anisotropic.yaml ${DEMO_NAV2_PARAMS} &&
  sed -i \
    -e 's/ProxemicForce.scale: 32.0/ProxemicForce.scale: 80.0/' \
    -e 's/ProxemicForce.comfort_distance: 1.0/ProxemicForce.comfort_distance: 3.0/' \
    -e 's/ProxemicForce.sigma: 0.4/ProxemicForce.sigma: 0.35/' \
    -e 's/ProxemicForce.ignored_identifiers: \[visitor_1\]/ProxemicForce.ignored_identifiers: []/' \
    -e 's/PathAlign.scale: 16.0/PathAlign.scale: 10.0/' \
    -e 's/PathDist.scale: 20.0/PathDist.scale: 12.0/' \
    ${DEMO_NAV2_PARAMS}
"

SIMULATION_REMOTE="${ROS_SETUP} && exec ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py gzclient:=True publish_people:=True use_scripted_visitor:=False use_engagement:=False use_language:=False use_speech:=False nav2_params_file:=${DEMO_NAV2_PARAMS}"
printf -v simulation_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${SIMULATION_REMOTE}"
open_terminal "TIAGO - SIMULATION" "simulation" "${simulation_command}"

gazebo_ready() {
  local services
  services="$(ros_exec "ros2 service list" 2>/dev/null)" || return 1
  grep -Fxq "/gazebo/set_entity_state" <<<"${services}" && grep -Fxq "/spawn_entity" <<<"${services}"
}

nav2_ready() {
  local actions controller navigator
  actions="$(ros_exec "ros2 action list" 2>/dev/null)" || return 1
  grep -Fxq "/navigate_to_pose" <<<"${actions}" || return 1
  controller="$(ros_exec "ros2 lifecycle get /controller_server" 2>/dev/null)" || return 1
  navigator="$(ros_exec "ros2 lifecycle get /bt_navigator" 2>/dev/null)" || return 1
  grep -Eq '^active \[3\]$' <<<"${controller}" && grep -Eq '^active \[3\]$' <<<"${navigator}"
}

print_nav2_state() {
  local controller navigator
  controller="$(ros_exec "ros2 lifecycle get /controller_server" 2>/dev/null || true)"
  navigator="$(ros_exec "ros2 lifecycle get /bt_navigator" 2>/dev/null || true)"
  echo "  controller_server: ${controller:-not available}"
  echo "  bt_navigator:      ${navigator:-not available}"
}

robot_at_demo_start() {
  local position x y
  position="$(ros_exec "timeout 5 ros2 topic echo /museum/ground_truth_odom --once --field pose.pose.position" 2>/dev/null)" || return 1
  x="$(awk '$1 == "x:" {print $2; exit}' <<<"${position}")"
  y="$(awk '$1 == "y:" {print $2; exit}' <<<"${position}")"
  awk -v x="${x}" -v y="${y}" 'BEGIN {exit !(x != "" && y != "" && sqrt(x*x+y*y) <= 0.50)}'
}

# Open the people and monitor windows as soon as Gazebo itself is alive.
# Previously these were opened only AFTER Nav2 became active, so when Nav2
# activation was slow/stuck the user saw only Gazebo and no other windows.
echo "Waiting for Gazebo services..."
deadline=$((SECONDS + 180))
until gazebo_ready; do
  if ((SECONDS >= deadline)); then
    echo "Timed out waiting for Gazebo services. Check TIAGO - SIMULATION." >&2
    exit 1
  fi
  sleep 2
done

echo "Gazebo services READY. Opening static-people and social-monitor windows now."

STATIC_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_static_people.py --ros-args -p use_sim_time:=true"
printf -v static_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${STATIC_REMOTE}"
open_terminal "TIAGO - STATIC PEOPLE" "crowd" "${static_command}"

MONITOR_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_social_monitor.py"
printf -v monitor_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${MONITOR_REMOTE}"
open_terminal "TIAGO - SOCIAL MONITOR" "monitor" "${monitor_command}"

echo "Waiting for Nav2 to become ACTIVE..."
deadline=$((SECONDS + 300))
next_report=$SECONDS
until nav2_ready; do
  if ((SECONDS >= next_report)); then
    print_nav2_state
    next_report=$((SECONDS + 10))
  fi
  if ((SECONDS >= deadline)); then
    echo "Timed out waiting for Nav2 ACTIVE." >&2
    print_nav2_state >&2
    echo "Gazebo, static people and monitor remain open for diagnosis." >&2
    exit 1
  fi
  sleep 2
done

echo "Nav2 ACTIVE."

if ! robot_at_demo_start; then
  echo "TIAGo is not near the expected start (0,0)." >&2
  echo "Gazebo, static people and monitor remain open for diagnosis." >&2
  exit 1
fi

people_ready() {
  local snapshot count
  snapshot="$(ros_exec "timeout 5 ros2 topic echo /people --once" 2>/dev/null)" || return 1
  count="$(grep -c 'identifier:' <<<"${snapshot}" || true)"
  [[ "${count}" -eq 10 ]]
}

echo "Waiting for all 10 static pedestrians on /people..."
deadline=$((SECONDS + 120))
until people_ready; do
  if ((SECONDS >= deadline)); then
    echo "Timed out waiting for ten people. Check TIAGO - STATIC PEOPLE and TIAGO - SOCIAL MONITOR." >&2
    exit 1
  fi
  sleep 2
done

echo "10 pedestrians READY. Opening Video Control."

read -r -d '' CONTROL_TEXT <<EOF || true
clear
printf '%s\n' \
'============================================' \
' TIAGO MUSEUM GUIDE - VIDEO 1 SOCIAL DEMO' \
'============================================' \
'' \
'Gazebo GUI: ON' \
'Nav2: ACTIVE' \
'People: 10 STATIC / 3 GROUPS' \
'Social comfort target: 3.0 m' \
'ProxemicForce scale: 80' \
'Goal: NORTH GALLERY (0.0, 16.0)' \
'' \
'Centre/right route is socially occupied.' \
'TIAGo should prefer a visible leftward detour.' \
'============================================'
for n in 8 7 6 5 4 3 2 1; do
  printf '\rNavigation starts in %2d s ' "\$n"
  sleep 1
done
printf '\nNAVIGATION GOAL SENT -> NORTH GALLERY\n'
exec ros2 run museum_assistant send_nav_goal --x ${GOAL_X} --y ${GOAL_Y} --yaw ${GOAL_YAW}
EOF
CONTROL_REMOTE="${ROS_SETUP} && ${CONTROL_TEXT}"
printf -v control_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${CONTROL_REMOTE}"
open_terminal "TIAGO - VIDEO CONTROL" "control" "${control_command}"

echo "Video 1 social demo started."
echo "Gazebo GUI: ON | People: 10 static | Groups: 3 | Comfort target: 3.0 m"
echo "TIAGo starts automatically after ${AUTO_START_DELAY}s."
echo "Stop with: ./scripts/stop_video1_demo.sh"
