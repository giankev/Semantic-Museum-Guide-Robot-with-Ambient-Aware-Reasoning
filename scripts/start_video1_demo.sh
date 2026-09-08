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
DEMO_NAV2_PARAMS="/tmp/nav2_video1_single_goal.yaml"

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

# Single-goal social-navigation profile.  No intermediate waypoint is used.
# The values are deliberately less aggressive than the previous 3m/scale80
# experiment: TIAGo should drive straight first, then prefer a curved motion
# when the first group enters the local social influence zone, rather than
# finding in-place rotation cheaper than forward motion.
echo "Preparing single-goal social-navigation profile..."
docker exec "${CONTAINER}" bash -lc "
  cp /root/exchange/exchange/museum_ws/src/museum_assistant/config/nav2_supplied_anisotropic.yaml ${DEMO_NAV2_PARAMS} &&
  sed -i \
    -e 's/ProxemicForce.scale: 32.0/ProxemicForce.scale: 45.0/' \
    -e 's/ProxemicForce.comfort_distance: 1.0/ProxemicForce.comfort_distance: 2.4/' \
    -e 's/ProxemicForce.sigma: 0.4/ProxemicForce.sigma: 0.50/' \
    -e 's/ProxemicForce.ignored_identifiers: \[visitor_1\]/ProxemicForce.ignored_identifiers: [__none__]/' \
    -e 's/sim_time: 1.7/sim_time: 2.5/' \
    ${DEMO_NAV2_PARAMS}
  grep -E 'ProxemicForce.(scale|comfort_distance|sigma|ignored_identifiers)|sim_time:' ${DEMO_NAV2_PARAMS}
"

SIMULATION_REMOTE="${ROS_SETUP} && exec ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py gzclient:=True publish_people:=True use_scripted_visitor:=False use_engagement:=False use_language:=False use_speech:=False nav2_params_file:=${DEMO_NAV2_PARAMS}"
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

echo "Gazebo READY. Opening people, monitor and control."

STATIC_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_static_people.py --ros-args -p use_sim_time:=true"
printf -v static_command 'docker exec -it %q bash -lc %q' "${CONTAINER}" "${STATIC_REMOTE}"
open_terminal "TIAGO - STATIC PEOPLE" "crowd" "${static_command}"

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

  clear
  printf '%s\n' \
  '============================================' \
  ' TIAGO MUSEUM GUIDE - VIDEO 1 CONTROL' \
  '============================================' \
  "controller_server: \${controller:-waiting}" \
  "bt_navigator:      \${navigator:-waiting}" \
  "people on /people: \$people_count / 10" \
  "near-spawn visitor removed: \$([[ \$visitor_present -eq 0 ]] && echo YES || echo waiting)" \
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
echo "Only north_gallery (0,16) is sent. No waypoint route exists in this script."
echo "visitor_marker next to spawn is deleted before navigation starts."
echo "Stop with: ./scripts/stop_video1_demo.sh"
