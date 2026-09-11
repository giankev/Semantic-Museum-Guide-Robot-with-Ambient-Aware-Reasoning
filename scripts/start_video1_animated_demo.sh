#!/usr/bin/env bash
# Isolated ONE-ACTOR POC. This is not a runtime-accepted final crowd demo.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="museum_video1_animated_${UID}"
MODE=actor
GUI=True
OBSERVE=()
AUDIT=()
GOAL_TIME=60
for argument in "$@"; do
  case "${argument}" in
    --baseline) MODE=baseline ;;
    --static) MODE=static ;;
    --headless) GUI=False ;;
    --observe-only) OBSERVE=(--observe-only) ;;
    --runtime-audit) AUDIT=(--runtime-audit) ;;
    --goal-time=*) GOAL_TIME="${argument#*=}" ;;
    --help|-h)
      echo "Usage: $0 [--baseline|--static] [--headless] [--observe-only] [--runtime-audit] [--goal-time=60]"
      echo 'Default: one walking-actor proof of concept, NOT an accepted final crowd.'
      echo 'No crowd expansion is enabled before the one-actor runtime test passes.'
      exit 0 ;;
    *) echo "Unknown argument: ${argument}" >&2; exit 2 ;;
  esac
done
[[ "${GOAL_TIME}" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo 'Invalid goal time' >&2; exit 2; }
command -v docker >/dev/null || { echo 'Docker is required on the simulation host.' >&2; exit 1; }
docker image inspect museum-tiago:humble >/dev/null || {
  echo 'Build the existing museum-tiago:humble image first; no host ROS installation is needed.' >&2; exit 1;
}
if docker container inspect "${CONTAINER}" >/dev/null 2>&1; then
  echo "${CONTAINER} already exists. Stop its demo with scripts/stop_video1_animated_demo.sh." >&2
  exit 1
fi

DOMAIN="${VIDEO1_ROS_DOMAIN_ID:-107}"
[[ "${DOMAIN}" =~ ^[0-9]+$ ]] && ((10#${DOMAIN} > 0 && 10#${DOMAIN} < 201)) || {
  echo 'VIDEO1_ROS_DOMAIN_ID must be in 1..200 to isolate the experiment.' >&2; exit 2;
}
RUN_NAME="$(date -u +%Y%m%dT%H%M%SZ)_${MODE}"
RUN_DIR="${REPO_ROOT}/log/video1_animated/${RUN_NAME}"
REMOTE_RUN="/root/exchange/log/video1_animated/${RUN_NAME}"
mkdir -p "${RUN_DIR}/gazebo" "${RUN_DIR}/ros"
GPU_ARGS=()
if [[ "${VIDEO1_SOFTWARE_RENDERING:-0}" == 1 ]]; then
  GPU_ARGS=(-e LIBGL_ALWAYS_SOFTWARE=1 -e GALLIUM_DRIVER=llvmpipe)
elif command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then
  GPU_ARGS=(--gpus all)
elif [[ -d /dev/dri ]]; then
  GPU_ARGS=(--device=/dev/dri:/dev/dri -e LIBGL_ALWAYS_SOFTWARE=0)
else
  GPU_ARGS=(-e LIBGL_ALWAYS_SOFTWARE=1 -e GALLIUM_DRIVER=llvmpipe)
fi
GUI_ARGS=()
if [[ "${GUI}" == True || -n "${DISPLAY:-}" ]]; then
  # Match the validated desktop launcher, including its local X access rule.
  xhost +local:docker >"${RUN_DIR}/xhost.txt" 2>&1 || true
  GUI_ARGS=(-e "DISPLAY=${DISPLAY:-:0}" -e QT_X11_NO_MITSHM=1 -v /tmp/.X11-unix:/tmp/.X11-unix:rw)
fi
if [[ "${GUI}" == False && -z "${DISPLAY:-}" ]]; then
  echo 'GPU LiDAR requires an X display even without GUI. Set DISPLAY to the simulation desktop.' >&2
  exit 2
fi

OWNED=0
RUNTIME_STARTED=0
STATS_PID=''
cleanup_error() {
  local code=$?
  if [[ -n "${STATS_PID}" ]]; then kill "${STATS_PID}" 2>/dev/null || true; fi
  if ((code != 0 && OWNED == 1)); then
    echo "Video 1 POC failed (exit ${code}); evidence retained in ${RUN_DIR}" >&2
    for logfile in preparation.log runtime.log; do
      if [[ -f "${RUN_DIR}/${logfile}" ]]; then tail -n 12 "${RUN_DIR}/${logfile}" >&2; fi
    done
    if ((RUNTIME_STARTED == 0)); then
      docker stop --time 10 "${CONTAINER}" >/dev/null 2>&1 || true
    else
      echo "Gazebo/RViz retained for inspection. Stop: ./scripts/stop_video1_animated_demo.sh" >&2
    fi
  fi
}
trap cleanup_error EXIT
trap 'exit 130' INT TERM
docker run --rm -d --init --name "${CONTAINER}" --label org.museum.video1=animated-poc \
  --network=host -e "ROS_DOMAIN_ID=${DOMAIN}" \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp "${GPU_ARGS[@]}" "${GUI_ARGS[@]}" \
  -v "${RUN_DIR}/gazebo:/root/.gazebo" -v "${RUN_DIR}/ros:/root/.ros/log" \
  -v "${REPO_ROOT}:/root/exchange" -w /root/exchange museum-tiago:humble sleep infinity >/dev/null
OWNED=1
BUILD_SETUP='source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash'
SETUP="${BUILD_SETUP} && source /root/exchange/exchange/museum_ws/install/setup.bash"
PACKAGE='/root/exchange/exchange/museum_ws/src/museum_video1_actors'

docker exec "${CONTAINER}" bash -c "${BUILD_SETUP} && python3 - <<'PY'
import rclpy
from rclpy.node import Node
import time
rclpy.init()
n=Node('video1_domain_preflight')
end=time.monotonic()+2
while time.monotonic()<end:
    rclpy.spin_once(n, timeout_sec=0.1)
nodes=n.get_node_names()
conflicts=set(nodes) & {'gazebo', 'controller_server', 'bt_navigator'}
n.destroy_node()
rclpy.shutdown()
if conflicts:
    raise SystemExit(f'Another simulation uses this ROS domain: {conflicts}. Choose VIDEO1_ROS_DOMAIN_ID.')
PY"

echo 'Building isolated actor POC and required museum packages (sequentially for 8 GB RAM)...'
docker exec "${CONTAINER}" bash -c "${BUILD_SETUP} && cd /root/exchange/exchange/museum_ws && colcon build --symlink-install --executor sequential --packages-select museum_assistant museum_social_critic museum_video1_actors" \
  2>&1 | tee "${RUN_DIR}/build.log"
docker exec "${CONTAINER}" bash -c "${SETUP} && cd /root/exchange/exchange/museum_ws && colcon test --packages-select museum_video1_actors --event-handlers console_direct+ && colcon test-result --test-result-base build/museum_video1_actors --verbose" \
  2>&1 | tee "${RUN_DIR}/tests.log"
docker exec "${CONTAINER}" bash -c 'version=$(pkg-config --modversion gazebo) || exit $?; [[ "${version}" == 11.* ]] || { echo "Gazebo Classic 11 required; found ${version}" >&2; exit 1; }'
docker exec "${CONTAINER}" bash -c "${SETUP} && echo \"Gazebo Classic version: \$(pkg-config --modversion gazebo)\" && { dpkg-query -W gazebo libgazebo11 ros-humble-nav2-controller ros-humble-nav2-dwb-controller ros-humble-gazebo-ros || true; } && ros2 interface show social_nav_msgs/msg/Pedestrians && ros2 interface show social_nav_msgs/msg/Pedestrian" \
  >"${RUN_DIR}/versions.txt" 2>&1
# No extra graphics package is installed. Ogre logs below retain the actual
# Gazebo renderer if it gets far enough to create a GL context.
docker exec "${CONTAINER}" bash -c '
printf "DISPLAY=%s\nXAUTHORITY=%s\nLIBGL_ALWAYS_SOFTWARE=%s\nGALLIUM_DRIVER=%s\n" "${DISPLAY:-unset}" "${XAUTHORITY:-unset}" "${LIBGL_ALWAYS_SOFTWARE:-unset}" "${GALLIUM_DRIVER:-unset}"
id
ls -ld /tmp/.X11-unix
ls -l /tmp/.X11-unix /dev/dri 2>/dev/null || true
if command -v glxinfo >/dev/null; then timeout 10 glxinfo -B; echo "glxinfo exit=$?"; else echo "glxinfo unavailable: renderer NOT_MEASURED; inspect gazebo/*/ogre.log after startup"; fi
if command -v nvidia-smi >/dev/null; then nvidia-smi; echo "nvidia-smi exit=$?"; fi
' >"${RUN_DIR}/graphics.txt" 2>&1
docker exec "${CONTAINER}" bash -c '
printf "ROS_DOMAIN_ID=%s\nROS_LOCALHOST_ONLY=%s\nRMW_IMPLEMENTATION=%s\nCYCLONEDDS_URI=%s\n" "${ROS_DOMAIN_ID:-unset}" "${ROS_LOCALHOST_ONLY:-unset}" "${RMW_IMPLEMENTATION:-unset}" "${CYCLONEDDS_URI:-unset}"
for interface in /sys/class/net/*; do
  echo "$(basename "$interface") flags=$(cat "$interface/flags") state=$(cat "$interface/operstate")"
done
dpkg-query -W ros-humble-cyclonedds ros-humble-rmw-cyclonedds-cpp
' >"${RUN_DIR}/dds_environment.txt" 2>&1
docker inspect -f 'GPU={{json .HostConfig.DeviceRequests}} Devices={{json .HostConfig.Devices}} Image={{.Image}}' "${CONTAINER}" >"${RUN_DIR}/container.txt"
git -C "${REPO_ROOT}" rev-parse HEAD >"${RUN_DIR}/git_head.txt"
git -C "${REPO_ROOT}" status --porcelain >"${RUN_DIR}/git_status.txt"

docker exec "${CONTAINER}" bash -c "${SETUP} && python3 /root/exchange/scripts/prepare_video1_animated_world.py --source /root/exchange/exchange/museum_ws/src/museum_assistant/worlds/supplied_museum/museum_nav.world --output ${REMOTE_RUN}/museum.world --config ${PACKAGE}/config/one_actor.json --mode ${MODE}" \
  >"${RUN_DIR}/preparation.log" 2>&1
docker exec "${CONTAINER}" python3 -c 'import sys,yaml
from pathlib import Path
p=yaml.safe_load(Path(sys.argv[1]).read_text())
for d in p["Visualization Manager"]["Displays"]:
    if d.get("Class")=="rviz_default_plugins/RobotModel":
        d["Description Topic"]["Durability Policy"]="Transient Local"
p["Window Geometry"].update({"X":680,"Y":30,"Width":680,"Height":740})
Path(sys.argv[2]).write_text(yaml.safe_dump(p, sort_keys=False))' \
  /root/exchange/exchange/rviz/video1_social_navigation.rviz "${REMOTE_RUN}/video1.rviz"

# Preserve PAL's scoped model/plugin environment and launch ordering. Its
# gzclient command has no verbose argument, so add only that flag via PATH.
docker exec "${CONTAINER}" python3 -c 'import pathlib,shlex,shutil,sys
client=shutil.which("gzclient")
if client is None:
    raise SystemExit("gzclient executable missing")
wrapper=pathlib.Path(sys.argv[1])/"gzclient"
wrapper.parent.mkdir(parents=True, exist_ok=True)
wrapper.write_text("#!/bin/sh\nexec "+shlex.quote(client)+" --verbose \"$@\"\n")
wrapper.chmod(0o755)' "${REMOTE_RUN}/bin"

# Keep the source world, laser, map, all critic values and the static launcher intact.
# Gazebo reads its camera from the disposable world; no mouse/insert-model commands.
LAUNCH="${SETUP} && export PATH=\"${REMOTE_RUN}/bin:\${PATH}\" && export GAZEBO_PLUGIN_PATH=\"\$(ros2 pkg prefix museum_video1_actors)/lib:\${GAZEBO_PLUGIN_PATH:-}\" && exec ros2 launch museum_video1_actors video1.launch.py world_file:=${REMOTE_RUN}/museum.world mode:=${MODE} gzclient:=${GUI} rviz_config:=${REMOTE_RUN}/video1.rviz static_script:=/root/exchange/scripts/demo_static_people.py"
docker exec -d "${CONTAINER}" bash -c "${LAUNCH} >${REMOTE_RUN}/runtime.log 2>&1"
RUNTIME_STARTED=1
docker exec -d "${CONTAINER}" bash -c "${BUILD_SETUP} && timeout 1800 gz stats -p >${REMOTE_RUN}/gazebo_stats.csv 2>&1"
docker stats --format '{{json .}}' "${CONTAINER}" >"${RUN_DIR}/docker_stats.jsonl" 2>&1 &
STATS_PID=$!

echo "Evidence directory: ${RUN_DIR}"
echo 'The control below waits for ACTIVE Nav2, the exact critic parameters and measured actor motion.'
echo 'Navigation is scheduled at simulation time' "${GOAL_TIME}" 'seconds.'
TTY=()
[[ -t 0 && -t 1 ]] && TTY=(-t)
printf -v OBSERVE_ARG '%s' "${OBSERVE[*]}"
printf -v AUDIT_ARG '%s' "${AUDIT[*]}"
RECORDER_STATUS=0
docker exec -i "${TTY[@]}" "${CONTAINER}" bash -c "${SETUP} && exec ros2 run museum_video1_actors record_demo.py --output ${REMOTE_RUN} --mode ${MODE} --goal-time ${GOAL_TIME} ${OBSERVE_ARG} ${AUDIT_ARG} --ros-args -p use_sim_time:=true" || RECORDER_STATUS=$?
echo "Run finished. Gazebo/RViz remain open. Evidence: ${RUN_DIR}/summary.json"
echo 'This result does not promote the POC to an accepted final crowd demo.'
echo 'Stop: ./scripts/stop_video1_animated_demo.sh'
if ((RECORDER_STATUS != 0)); then
  echo "Recorder exited ${RECORDER_STATUS}; inspect summary.json and runtime.log. Simulation remains open." >&2
fi
if [[ -t 0 ]]; then
  read -r -p 'Press Enter to return to the shell (Gazebo/RViz stay open)... ' _ || true
fi
exit "${RECORDER_STATUS}"
