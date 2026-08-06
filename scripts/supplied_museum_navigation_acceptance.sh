#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="/root/exchange/exchange/museum_ws"
IMAGE="museum-tiago:humble"
RUN_LABEL="$(date -u +%Y%m%dT%H%M%SZ)"
RESULT_DIR="${REPO_ROOT}/.navigation_diagnostics/${RUN_LABEL}"
CONTAINER_RESULT_DIR="/root/exchange/.navigation_diagnostics/${RUN_LABEL}"
ACCEPT_BUILD="${CONTAINER_RESULT_DIR}/colcon/build"
ACCEPT_INSTALL="${CONTAINER_RESULT_DIR}/colcon/install"
ACCEPT_LOG="${CONTAINER_RESULT_DIR}/colcon/log"
ACTIVE_CONTAINER=""

mkdir -p "${RESULT_DIR}"

cleanup() {
  if [[ -n "${ACTIVE_CONTAINER}" ]]; then
    docker rm -f "${ACTIVE_CONTAINER}" >/dev/null 2>&1 || true
  fi
  xhost -local:docker >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if [[ "${1:-}" == "--validation" ]]; then
  DESTINATIONS=(
    central_gallery central_gallery north_gallery
    south_west_gallery south_west_gallery
    south_east_gallery south_east_gallery
  )
elif [[ "$#" -gt 0 ]]; then
  DESTINATIONS=("$@")
else
  DESTINATIONS=(
    central_gallery north_gallery south_west_gallery south_east_gallery
  )
fi

for destination in "${DESTINATIONS[@]}"; do
  case "${destination}" in
    central_gallery|north_gallery|south_west_gallery|south_east_gallery) ;;
    *)
      echo "Unsupported destination: ${destination}" >&2
      exit 64
      ;;
  esac
done

echo "Building and testing museum_assistant and museum_social_critic"
docker rm -f museum_nav_acceptance_build >/dev/null 2>&1 || true
docker run --rm \
  --name museum_nav_acceptance_build \
  --net=host \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  -v "${REPO_ROOT}:/root/exchange" \
  "${IMAGE}" \
  bash -lc "
    set -eo pipefail
    source /opt/ros/humble/setup.bash
    source /root/tiago_public_ws/install/setup.bash
    source /root/social_nav_ws/install/setup.bash 2>/dev/null || true
    cd ${WORKSPACE}
    colcon --log-base ${ACCEPT_LOG} build --symlink-install \\
      --build-base ${ACCEPT_BUILD} \\
      --install-base ${ACCEPT_INSTALL} \\
      --packages-select museum_assistant museum_social_critic \\
      --event-handlers console_cohesion+
    source ${ACCEPT_INSTALL}/setup.bash
    colcon --log-base ${ACCEPT_LOG} test \\
      --build-base ${ACCEPT_BUILD} \\
      --install-base ${ACCEPT_INSTALL} \\
      --packages-select museum_assistant museum_social_critic \\
      --event-handlers console_cohesion+
    colcon test-result --test-result-base ${ACCEPT_BUILD} --verbose
  " 2>&1 | tee "${RESULT_DIR}/build_and_test.log"

xhost +local:docker >/dev/null 2>&1 || true
GPU_ARGS=()
RENDER_ENV=()
if command -v nvidia-smi >/dev/null 2>&1 \
  && nvidia-smi >/dev/null 2>&1; then
  GPU_ARGS=(--gpus all)
else
  RENDER_ENV=(-e LIBGL_ALWAYS_SOFTWARE=1 -e GALLIUM_DRIVER=llvmpipe)
fi

declare -A COUNTS=()
for destination in "${DESTINATIONS[@]}"; do
  count=$(( ${COUNTS[${destination}]:-0} + 1 ))
  COUNTS[${destination}]="${count}"
  episode="${destination}_${count}"
  ACTIVE_CONTAINER="museum_nav_accept_${destination}_${count}"
  launch_log="${RESULT_DIR}/${episode}_launch.log"
  report_path="${RESULT_DIR}/${episode}.json"
  warnings_path="${RESULT_DIR}/${episode}_warnings.log"

  docker rm -f "${ACTIVE_CONTAINER}" >/dev/null 2>&1 || true
  echo "Starting clean episode ${episode}"
  docker run -d \
    --name "${ACTIVE_CONTAINER}" \
    --net=host \
    "${GPU_ARGS[@]}" \
    -e DISPLAY="${DISPLAY:-:0}" \
    -e QT_X11_NO_MITSHM=1 \
    -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    "${RENDER_ENV[@]}" \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v "${REPO_ROOT}:/root/exchange" \
    -w /root/exchange \
    "${IMAGE}" \
    bash -lc "
      set -eo pipefail
      source /opt/ros/humble/setup.bash
      source /root/tiago_public_ws/install/setup.bash
      source /root/social_nav_ws/install/setup.bash 2>/dev/null || true
      source ${ACCEPT_INSTALL}/setup.bash
      exec ros2 launch museum_assistant \\
        supplied_museum_demo_navigation.launch.py gzclient:=False \\
        > /root/exchange/.navigation_diagnostics/${RUN_LABEL}/${episode}_launch.log \\
        2>&1
    " >"${RESULT_DIR}/${episode}_container_id.txt"

  docker exec "${ACTIVE_CONTAINER}" bash -lc "
    source /opt/ros/humble/setup.bash
    source /root/tiago_public_ws/install/setup.bash
    source /root/social_nav_ws/install/setup.bash 2>/dev/null || true
    source ${ACCEPT_INSTALL}/setup.bash
    ready=false
    for attempt in \$(seq 1 150); do
      states=\$(for node in map_server amcl planner_server controller_server \\
        bt_navigator velocity_smoother; do
          ros2 lifecycle get /\${node} 2>/dev/null | tail -n 1
        done)
      if [[ \$(grep -c active <<<\"\${states}\") -eq 6 ]] \\
        && ros2 action list 2>/dev/null | grep -qx /navigate_to_pose \\
        && timeout 3 ros2 topic echo /scan_raw --once >/dev/null 2>&1 \\
        && timeout 3 ros2 topic echo /museum/ground_truth_odom \\
          --once >/dev/null 2>&1; then
        ready=true
        break
      fi
      sleep 1
    done
    [[ \"\${ready}\" == true ]]
    [[ \$(ros2 param get /controller_server FollowPath.plugin) \\
      == *dwb_core::DWBLocalPlanner* ]]
    [[ \$(ros2 param get /planner_server GridBased.allow_unknown) \\
      == *False* ]]
    [[ \$(ros2 param get /controller_server odom_topic) \\
      == */museum/ground_truth_odom* ]]
    [[ \$(ros2 param get /bt_navigator odom_topic) \\
      == */museum/ground_truth_odom* ]]
    [[ \$(ros2 param get /velocity_smoother odom_topic) \\
      == */museum/ground_truth_odom* ]]
    timeout 10 ros2 run tf2_ros tf2_echo map base_footprint 2>&1 \\
      | grep -m1 Translation
  " >"${RESULT_DIR}/${episode}_readiness.log" 2>&1

  set +e
  timeout --signal=INT --kill-after=20 1800 \
    docker exec "${ACTIVE_CONTAINER}" bash -lc "
      set -eo pipefail
      source /opt/ros/humble/setup.bash
      source /root/tiago_public_ws/install/setup.bash
      source /root/social_nav_ws/install/setup.bash 2>/dev/null || true
      source ${ACCEPT_INSTALL}/setup.bash
      ros2 run museum_assistant supplied_museum_route_runner \\
        --destination ${destination} \\
        --output /root/exchange/.navigation_diagnostics/${RUN_LABEL}/${episode}.json \\
        --ros-args -p use_sim_time:=true
    " >"${RESULT_DIR}/${episode}_runner.log" 2>&1
  episode_status=$?
  set -e

  grep -Ei \
    "warn|error|failed|collision|recovery|oscillat|progress" \
    "${launch_log}" >"${warnings_path}" || true
  docker rm -f "${ACTIVE_CONTAINER}" >/dev/null 2>&1 || true
  ACTIVE_CONTAINER=""

  if [[ "${episode_status}" -ne 0 ]]; then
    echo "Episode ${episode} failed with exit code ${episode_status}" >&2
    exit "${episode_status}"
  fi
  python3 - "${report_path}" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if report.get("status") != "passed":
    raise SystemExit(f"Acceptance report failed: {report}")
print(
    f"PASS {report['destination']}: "
    f"{len(report['waypoints'])} waypoint(s), "
    f"Gazebo error {report['final']['gazebo_target_error_m']:.3f} m"
)
PY
done

echo "All requested episodes passed. Reports: ${RESULT_DIR}"
