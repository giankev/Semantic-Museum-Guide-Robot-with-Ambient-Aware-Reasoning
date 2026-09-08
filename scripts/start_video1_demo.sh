#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="museum_tiago"
STATE_DIR="/tmp/tiago_video1_demo_${UID}"
ROS_SETUP="source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash && source /root/exchange/exchange/museum_ws/install/setup.bash"
BUILD_SETUP="source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash"
GOAL_X="0.0"
GOAL_Y="8.0"
GOAL_YAW="1.57"

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
rm -f "${STATE_DIR}/container_started"

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

container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null || true)" == "true" ]]
}

xhost +local:docker >/dev/null 2>&1 || true

if ! docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  printf -v container_command 'cd %q && exec ./start_museum_tiago.sh' "${REPO_ROOT}"
  open_terminal "TIAGO - CONTAINER" "container" "${container_command}"
  touch "${STATE_DIR}/container_started"
elif ! container_running; then
  printf -v container_command 'exec docker start -ai %q' "${CONTAINER}"
  open_terminal "TIAGO - CONTAINER" "container" "${container_command}"
  touch "${STATE_DIR}/container_started"
fi

deadline=$((SECONDS + 90))
until container_running; do
  if ((SECONDS >= deadline)); then
    echo "Timed out waiting for ${CONTAINER}." >&2
    exit 1
  fi
  sleep 1
done

docker exec "${CONTAINER}" test -d /root/exchange/exchange/museum_ws || {
  echo "${CONTAINER} does not contain the expected /root/exchange mount." >&2
  exit 1
}

existing_topics="$(
  docker exec "${CONTAINER}" bash -lc \
    "source /opt/ros/humble/setup.bash && ros2 topic list" 2>/dev/null || true
)"
existing_actions="$(
  docker exec "${CONTAINER}" bash -lc \
    "source /opt/ros/humble/setup.bash && ros2 action list" 2>/dev/null || true
)"
existing_nodes="$(
  docker exec "${CONTAINER}" bash -lc \
    "source /opt/ros/humble/setup.bash && ros2 node list" 2>/dev/null || true
)"
if grep -Fxq "/gazebo/model_states" <<<"${existing_topics}" \
  || grep -Fxq "/navigate_to_pose" <<<"${existing_actions}" \
  || grep -Eq '^/(gazebo|controller_server|bt_navigator|simulation_ground_truth_odom|demo_crowd_motion)$' \
    <<<"${existing_nodes}"; then
  echo "An existing Gazebo/Nav2 runtime is active in ${CONTAINER}." >&2
  echo "Stop that runtime before starting Video 1; no processes were killed." >&2
  exit 1
fi

echo "Building the two workspace packages needed by the demo..."
docker exec "${CONTAINER}" bash -lc \
  "${BUILD_SETUP} && cd /root/exchange/exchange/museum_ws && colcon build --symlink-install --packages-select museum_assistant museum_social_critic"

SIMULATION_REMOTE="${ROS_SETUP} && exec ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py gzclient:=True publish_people:=True use_engagement:=False use_language:=False use_speech:=False nav2_params_file:=/root/exchange/exchange/museum_ws/src/museum_assistant/config/nav2_supplied_anisotropic.yaml"
printf -v simulation_command 'docker exec -it %q bash -lc %q' \
  "${CONTAINER}" "${SIMULATION_REMOTE}"
open_terminal "TIAGO - SIMULATION" "simulation" "${simulation_command}"

ros_exec() {
  docker exec "${CONTAINER}" bash -lc "${ROS_SETUP} && $1"
}

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
  position="$(
    ros_exec "timeout 5 ros2 topic echo /museum/ground_truth_odom --once --field pose.pose.position" 2>/dev/null
  )" || return 1
  x="$(awk '$1 == "x:" {print $2; exit}' <<<"${position}")"
  y="$(awk '$1 == "y:" {print $2; exit}' <<<"${position}")"
  awk -v x="${x}" -v y="${y}" \
    'BEGIN {exit !(x != "" && y != "" && sqrt(x * x + y * y) <= 0.50)}'
}

echo "Waiting for Gazebo services and active Nav2 nodes..."
deadline=$((SECONDS + 300))
until gazebo_ready && nav2_ready; do
  if ((SECONDS >= deadline)); then
    echo "Timed out waiting for Gazebo/Nav2. Run scripts/stop_video1_demo.sh." >&2
    exit 1
  fi
  sleep 2
done

if ! robot_at_demo_start; then
  echo "TIAGo is not at the expected Video 1 start near (0, 0)." >&2
  echo "Refusing to send a potentially trivial or stale navigation goal." >&2
  exit 1
fi

CROWD_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_crowd_motion.py --seed 42 --count 6 --ros-args -p use_sim_time:=true"
printf -v crowd_command 'docker exec -it %q bash -lc %q' \
  "${CONTAINER}" "${CROWD_REMOTE}"
open_terminal "TIAGO - CROWD" "crowd" "${crowd_command}"

MONITOR_REMOTE="${ROS_SETUP} && exec python3 /root/exchange/scripts/demo_monitor.py"
printf -v monitor_command 'docker exec -it %q bash -lc %q' \
  "${CONTAINER}" "${MONITOR_REMOTE}"
open_terminal "TIAGO - MONITOR" "monitor" "${monitor_command}"

people_ready() {
  local people count moving
  people="$(ros_exec "timeout 5 ros2 topic echo /people --once" 2>/dev/null)" || return 1
  read -r count moving < <(
    awk '
      function finish_person() {
        if (person && sqrt(vx * vx + vy * vy) >= 0.05) moving++
      }
      /^[[:space:]]*-[[:space:]]+identifier:/ {
        finish_person()
        person = 1
        people++
        velocity = 0
        vx = 0
        vy = 0
        next
      }
      person && /^[[:space:]]+velocity:/ {
        velocity = 1
        next
      }
      velocity && /^[[:space:]]+x:/ {
        vx = $2
        next
      }
      velocity && /^[[:space:]]+y:/ {
        vy = $2
        velocity = 0
        next
      }
      END {
        finish_person()
        print people + 0, moving + 0
      }
    ' <<<"${people}"
  )
  [[ "${count}" -eq 6 && "${moving}" -eq 6 ]]
}

anisotropic_ready() {
  local value
  value="$(ros_exec "ros2 param get /controller_server FollowPath.ProxemicForce.anisotropic_enabled" 2>/dev/null)" || return 1
  grep -qi "true" <<<"${value}"
}

nav2_speed_limit_ready() {
  local controller_limit smoother_limit
  controller_limit="$(
    ros_exec "ros2 param get /controller_server FollowPath.max_vel_x" 2>/dev/null
  )" || return 1
  smoother_limit="$(
    ros_exec "ros2 param get /velocity_smoother max_velocity" 2>/dev/null
  )" || return 1
  grep -Eq '(^|[^0-9])0\.2(0)?([^0-9]|$)' <<<"${controller_limit}" \
    && grep -Eq '\[0\.2(0)?,' <<<"${smoother_limit}"
}

sim_time_ns() {
  local clock sec nanosec
  clock="$(ros_exec "timeout 5 ros2 topic echo /clock --once" 2>/dev/null)" \
    || return 1
  sec="$(awk '$1 == "sec:" {print $2; exit}' <<<"${clock}")"
  nanosec="$(awk '$1 == "nanosec:" {print $2; exit}' <<<"${clock}")"
  [[ "${sec}" =~ ^[0-9]+$ && "${nanosec}" =~ ^[0-9]+$ ]] || return 1
  printf '%s\n' "$((sec * 1000000000 + nanosec))"
}

echo "Waiting for six moving pedestrians and the anisotropic critic..."
deadline=$((SECONDS + 120))
until people_ready && anisotropic_ready && nav2_speed_limit_ready; do
  if ((SECONDS >= deadline)); then
    echo "Timed out waiting for the complete social-navigation demo." >&2
    exit 1
  fi
  sleep 2
done

echo "Allowing five simulated seconds of crowd warm-up..."
warmup_start_sim="$(sim_time_ns)" || {
  echo "Could not read the Gazebo simulation clock." >&2
  exit 1
}
warmup_start_wall="$(date +%s%N)"
deadline=$((SECONDS + 120))
while true; do
  warmup_now_sim="$(sim_time_ns)" || warmup_now_sim="${warmup_start_sim}"
  if ((warmup_now_sim - warmup_start_sim >= 5000000000)); then
    break
  fi
  if ((SECONDS >= deadline)); then
    echo "Timed out during the crowd warm-up." >&2
    exit 1
  fi
  sleep 1
done
warmup_end_wall="$(date +%s%N)"
REAL_TIME_FACTOR="$(
  awk -v sim_ns="$((warmup_now_sim - warmup_start_sim))" \
    -v wall_ns="$((warmup_end_wall - warmup_start_wall))" \
    'BEGIN {if (wall_ns > 0) printf "%.2f", sim_ns / wall_ns; else print "unknown"}'
)"

read -r -d '' CONTROL_TEXT <<EOF || true
clear
printf '%s\n' \
'============================================' \
' TIAGO MUSEUM GUIDE - VIDEO 1 READY' \
'============================================' \
'' \
'Gazebo: READY' \
'Nav2: READY' \
'People: 6' \
'Moving: 6' \
'Social critic: ANISOTROPIC' \
'TIAGo controlled by Nav2: YES' \
'TIAGo Nav2 speed limit: 0.20 m/s' \
'Crowd layout: 3 crossing lanes + 3 lateral lanes' \
'Crowd warm-up: 5 simulated seconds' \
'Gazebo real-time factor: ${REAL_TIME_FACTOR}' \
'Goal: (0.0, 8.0)' \
'' \
'Start the screen recording now.' \
'' \
'Press ENTER to start TIAGo navigation.' \
'============================================'
read -r _
printf 'Starting in '
for n in 3 2 1; do
  printf '%s... ' "$n"
  sleep 1
done
printf '\nNAVIGATION START\n'
exec ros2 run museum_assistant send_nav_goal --x ${GOAL_X} --y ${GOAL_Y} --yaw ${GOAL_YAW}
EOF
CONTROL_REMOTE="${ROS_SETUP} && ${CONTROL_TEXT}"
printf -v control_command 'docker exec -it %q bash -lc %q' \
  "${CONTAINER}" "${CONTROL_REMOTE}"
open_terminal "TIAGO - VIDEO CONTROL" "control" "${control_command}"

echo "Video 1 is ready. Use scripts/stop_video1_demo.sh when recording is complete."
