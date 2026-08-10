#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_NAME="museum-tiago:humble"
CONTAINER_NAME="museum_final_end_to_end_acceptance"
WORKSPACE="/root/exchange/exchange/museum_ws"
BUILD_ROOT="/tmp/museum_final_end_to_end_colcon"
BUILD_BASE="${BUILD_ROOT}/build"
INSTALL_BASE="${BUILD_ROOT}/install"
LOG_BASE="${BUILD_ROOT}/log"
TRIAL="${E2E_TRIAL:-}"
CAMPAIGN_ID="${E2E_CAMPAIGN_ID:-e2e_campaign_$(date -u +%Y%m%dT%H%M%SZ)}"
RESULT_DIR="${REPO_ROOT}/.navigation_diagnostics/${CAMPAIGN_ID}/trial_${TRIAL}_artifacts"
REPORT_PATH="${REPO_ROOT}/.navigation_diagnostics/${CAMPAIGN_ID}/trial_${TRIAL}.json"
CONTAINER_RESULT_DIR="/root/exchange/.navigation_diagnostics/${CAMPAIGN_ID}/trial_${TRIAL}_artifacts"
CONTAINER_AUDIO="${CONTAINER_RESULT_DIR}/request.wav"
ROS_DOMAIN_ID="79"
ROS_SETUP="source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash && source ${INSTALL_BASE}/setup.bash && export ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
EXPECTED_TEXT="Portami a vedere qualcosa di impressionista"

CONTAINER_STARTED=false
XHOST_ENABLED=false
COPIED_AUDIO=""
ROS_PIDS=()
ROS_DESCRIPTIONS=()
LAST_PID=""
EXPERIMENT_STARTED=false
FAILURE_STAGE="preflight"
FAILURE_REASON=""

die() {
  FAILURE_REASON="$*"
  echo "ERROR: $*" >&2
  exit 1
}

write_incomplete_report() {
  local status="invalid_run"
  [[ "${EXPERIMENT_STARTED}" == true ]] && status="failed"
  mkdir -p "$(dirname "${REPORT_PATH}")"
  python3 - "${REPORT_PATH}" "${status}" "${TRIAL:-}" \
    "${FAILURE_STAGE}" "${FAILURE_REASON:-runner exited unexpectedly}" \
    "$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo NA)" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
status, trial, stage, reason, commit = sys.argv[2:]
report = {
    "benchmark": "end_to_end",
    "run_id": f"end-to-end-{trial}",
    "trial": int(trial) if trial.isdigit() else None,
    "campaign_git_commit": commit,
    "scenario": "audio_impressionism_north_gallery",
    "variant": "groq_whisper_anisotropic_engagement_required",
    "configuration": "engagement_required_groq_stt_anisotropic",
    "status": status,
    "stage": stage,
    "failure_reason": reason,
    "wav_source": "external_host_file_not_retained",
}
path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

container_bash() {
  docker exec "${CONTAINER_NAME}" bash -lc "$1"
}

process_alive() {
  local pid=${1:-}
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  container_bash "ps -eo pgid=,stat= | awk -v target='${pid}' \
    '\$1 == target && \$2 !~ /^Z/ { found=1 } \
    END { exit(found ? 0 : 1) }'" >/dev/null 2>&1
}

start_process() {
  local log_name=$1
  local command=$2
  local description=${3:-${command}}
  local log_path="${CONTAINER_RESULT_DIR}/${log_name}"

  LAST_PID="$(container_bash \
    "nohup setsid bash -lc '${ROS_SETUP} && exec ${command}' > '${log_path}' 2>&1 < /dev/null & echo \$!")"
  [[ "${LAST_PID}" =~ ^[0-9]+$ ]] || die "Could not start ${description}."
  ROS_PIDS+=("${LAST_PID}")
  ROS_DESCRIPTIONS+=("${description}")
}

stop_process_group() {
  local pid=${1:-}
  local attempt
  process_alive "${pid}" || return 0
  container_bash "kill -TERM -- -${pid} >/dev/null 2>&1 || true" || true
  for attempt in {1..20}; do
    process_alive "${pid}" || return 0
    sleep 0.25
  done
  container_bash "kill -KILL -- -${pid} >/dev/null 2>&1 || true" || true
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  set +e
  local index
  if [[ "${CONTAINER_STARTED}" == true ]]; then
    for ((index = ${#ROS_PIDS[@]} - 1; index >= 0; index--)); do
      stop_process_group "${ROS_PIDS[index]}" >/dev/null 2>&1 || true
    done
    docker container rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  fi
  if [[ "${XHOST_ENABLED}" == true ]]; then
    xhost -local:docker >/dev/null 2>&1 || true
  fi
  [[ -z "${COPIED_AUDIO}" ]] || rm -f -- "${COPIED_AUDIO}"
  unset GROQ_API_KEY
  if [[ ${exit_code} -ne 0 ]]; then
    [[ -f "${REPORT_PATH}" ]] || write_incomplete_report
    echo "Acceptance diagnostics preserved at ${RESULT_DIR}" >&2
    echo "Campaign record: ${REPORT_PATH}" >&2
  fi
  exit "${exit_code}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ $# -eq 1 ]] || die "Usage: $0 /path/request.wav"
[[ "${TRIAL}" == "2" || "${TRIAL}" == "3" ]] \
  || die "Set E2E_TRIAL to 2 or 3."
[[ "${CAMPAIGN_ID}" == e2e_campaign_* ]] \
  || die "E2E_CAMPAIGN_ID must start with e2e_campaign_."
AUDIO_PATH=$1
[[ -f "${AUDIO_PATH}" ]] || die "WAV file does not exist: ${AUDIO_PATH}"
[[ -r "${AUDIO_PATH}" ]] || die "WAV file is not readable: ${AUDIO_PATH}"
[[ "${AUDIO_PATH,,}" == *.wav ]] || die "Final acceptance requires a WAV file."
(( $(stat -c '%s' -- "${AUDIO_PATH}") > 44 )) \
  || die "WAV file is empty or lacks audio frames."
python3 - "${AUDIO_PATH}" <<'PY'
import sys
import wave

try:
    with wave.open(sys.argv[1], "rb") as audio:
        assert audio.getnframes() > 0
except (AssertionError, EOFError, OSError, wave.Error) as exc:
    raise SystemExit(f"ERROR: invalid WAV input: {exc}")
PY

echo "Checking the repository diff..."
git -C "${REPO_ROOT}" diff --check
FAILURE_STAGE="docker_build"

if [[ -z "${GROQ_API_KEY:-}" ]]; then
  read -r -s -p "GROQ_API_KEY: " GROQ_API_KEY
  echo
fi
[[ -n "${GROQ_API_KEY:-}" ]] || die "GROQ_API_KEY is required."
export GROQ_API_KEY
export GROQ_BASE_URL="${GROQ_BASE_URL:-https://api.groq.com/openai/v1}"
export GROQ_MODEL="${GROQ_MODEL:-openai/gpt-oss-20b}"
export GROQ_STT_MODEL="${GROQ_STT_MODEL:-whisper-large-v3-turbo}"

if [[ "${FINAL_SKIP_DOCKER_BUILD:-0}" == "1" ]]; then
  docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1 \
    || die "FINAL_SKIP_DOCKER_BUILD=1 but local image ${IMAGE_NAME} does not exist."
  echo "Reusing local image ${IMAGE_NAME}; Docker build skipped."
else
  echo "Building ${IMAGE_NAME}..."
  docker build -f "${REPO_ROOT}/dockerfiles/Dockerfile.tiago_museum" \
    -t "${IMAGE_NAME}" "${REPO_ROOT}"
fi

mkdir -p "${RESULT_DIR}"
COPIED_AUDIO="${RESULT_DIR}/request.wav"
cp -- "${AUDIO_PATH}" "${COPIED_AUDIO}"

docker container rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
GPU_ARGS=()
RENDER_ENV=()
if command -v nvidia-smi >/dev/null 2>&1 \
  && nvidia-smi >/dev/null 2>&1; then
  GPU_ARGS=(--gpus all)
else
  RENDER_ENV=(-e LIBGL_ALWAYS_SOFTWARE=1 -e GALLIUM_DRIVER=llvmpipe)
fi
if command -v xhost >/dev/null 2>&1; then
  xhost +local:docker >/dev/null 2>&1 || true
  XHOST_ENABLED=true
fi

DOCKER_ENV_ARGS=(
  -e GROQ_API_KEY -e GROQ_BASE_URL -e GROQ_MODEL -e GROQ_STT_MODEL
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}"
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  -e DISPLAY="${DISPLAY:-:0}" -e QT_X11_NO_MITSHM=1
)
for name in HTTP_PROXY HTTPS_PROXY NO_PROXY ALL_PROXY \
  http_proxy https_proxy no_proxy all_proxy \
  SSL_CERT_FILE REQUESTS_CA_BUNDLE CURL_CA_BUNDLE; do
  [[ -z "${!name:-}" ]] || DOCKER_ENV_ARGS+=(-e "${name}")
done

echo "Starting dedicated acceptance container..."
FAILURE_STAGE="container_start"
docker run -d --name "${CONTAINER_NAME}" --init --net=host \
  "${GPU_ARGS[@]}" "${RENDER_ENV[@]}" "${DOCKER_ENV_ARGS[@]}" \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v "${REPO_ROOT}:/root/exchange" -w /root/exchange \
  "${IMAGE_NAME}" sleep infinity >/dev/null
CONTAINER_STARTED=true

echo "Clean-building and testing the complete selected workspace..."
FAILURE_STAGE="build_and_test"
container_bash "set -eo pipefail \
  && source /opt/ros/humble/setup.bash \
  && source /root/tiago_public_ws/install/setup.bash \
  && source /root/social_nav_ws/install/setup.bash \
  && cd ${WORKSPACE} \
  && colcon --log-base ${LOG_BASE} build --symlink-install \
    --build-base ${BUILD_BASE} --install-base ${INSTALL_BASE} \
    --packages-select museum_assistant museum_social_critic \
    --event-handlers console_cohesion+ \
  && source ${INSTALL_BASE}/setup.bash \
  && colcon --log-base ${LOG_BASE} test \
    --build-base ${BUILD_BASE} --install-base ${INSTALL_BASE} \
    --packages-select museum_assistant museum_social_critic \
    --event-handlers console_cohesion+ \
  && colcon test-result --test-result-base ${BUILD_BASE} --verbose" \
  2>&1 | tee "${RESULT_DIR}/build_and_test.log"

TEST_SUMMARY="$(grep '^Summary:' "${RESULT_DIR}/build_and_test.log" | tail -n 1)"
[[ "${TEST_SUMMARY}" =~ Summary:\ ([0-9]+)\ tests,\ ([0-9]+)\ errors,\ ([0-9]+)\ failures,\ ([0-9]+)\ skipped ]] \
  || die "Could not parse complete test totals."
(( BASH_REMATCH[2] == 0 && BASH_REMATCH[3] == 0 )) \
  || die "The complete test suite failed."

echo "Starting the existing supplied-museum full-stack launch..."
FAILURE_STAGE="runtime_startup"
start_process launch.log \
  "ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py gzclient:=False use_engagement:=True require_engagement:=True use_speech:=True use_language:=True publish_people:=True nav2_params_file:=${INSTALL_BASE}/museum_assistant/share/museum_assistant/config/nav2_supplied_anisotropic.yaml" \
  supplied_museum_reasoning_navigation
LAUNCH_PID=${LAST_PID}

start_process engagement_capture.log \
  "env PYTHONUNBUFFERED=1 timeout 1800 python3 /root/exchange/scripts/capture_json_string_topic.py --topic /museum/engagement_state --output ${CONTAINER_RESULT_DIR}/engagement_records.jsonl" \
  engagement_state_capture

echo "Placing the validated frontal visitor fixture for real RGB + LiDAR engagement..."
container_bash "${ROS_SETUP} && python3 /root/exchange/scripts/place_gazebo_entity.py --name visitor_marker --x 1.7 --y 0.0 --yaw -1.5707963267948966 --timeout 60"

echo "Waiting for Gazebo, AMCL, Nav2, engagement, speech, language, and session readiness..."
READY=false
for _attempt in $(seq 1 240); do
  if ! process_alive "${LAUNCH_PID}"; then
    die "The full-stack launch exited during startup."
  fi
  STATES="$(container_bash "${ROS_SETUP} && for node in map_server amcl planner_server controller_server bt_navigator velocity_smoother; do ros2 lifecycle get /\${node} 2>/dev/null | tail -n 1; done" 2>/dev/null || true)"
  TOPICS="$(container_bash "${ROS_SETUP} && ros2 topic list" 2>/dev/null || true)"
  if [[ $(grep -c active <<<"${STATES}") -eq 6 ]] \
    && grep -Fxq /navigate_to_pose <<<"$(container_bash "${ROS_SETUP} && ros2 action list" 2>/dev/null || true)" \
    && grep -Fxq /museum/audio_file <<<"${TOPICS}" \
    && grep -Fxq /museum/engagement_state <<<"${TOPICS}" \
    && grep -Fxq /museum/user_request <<<"${TOPICS}" \
    && grep -Fxq /museum/supplied_route_request <<<"${TOPICS}" \
    && grep -Fxq /museum/navigation_result <<<"${TOPICS}" \
    && grep -Fxq /people <<<"${TOPICS}"; then
    if container_bash "${ROS_SETUP} && timeout 3 ros2 topic echo /museum/session_state --field data --once" \
      >"${RESULT_DIR}/session_state.txt" 2>/dev/null \
      && grep -q '"session_id": "session_1"' "${RESULT_DIR}/session_state.txt" \
      && grep -q '"state": "active"' "${RESULT_DIR}/session_state.txt"; then
      READY=true
      break
    fi
  fi
  sleep 1
done
[[ "${READY}" == true ]] || die "Full-stack runtime did not become ready."

printf '%s\n' "${STATES}" >"${RESULT_DIR}/lifecycle_states.txt"
container_bash "${ROS_SETUP} && ros2 param get /controller_server FollowPath.plugin" \
  >"${RESULT_DIR}/controller_plugin.txt"
container_bash "${ROS_SETUP} && ros2 param get /controller_server FollowPath.critics" \
  >"${RESULT_DIR}/controller_critics.txt"
container_bash "${ROS_SETUP} && ros2 param get /controller_server FollowPath.ProxemicForce.class" \
  >"${RESULT_DIR}/proxemic_class.txt"
container_bash "${ROS_SETUP} && ros2 param get /controller_server FollowPath.ProxemicForce.people_topic" \
  >"${RESULT_DIR}/proxemic_people_topic.txt"
container_bash "${ROS_SETUP} && ros2 param get /controller_server FollowPath.ProxemicForce.ignored_identifiers" \
  >"${RESULT_DIR}/proxemic_ignored_identifiers.txt"
container_bash "${ROS_SETUP} && ros2 param get /controller_server FollowPath.ProxemicForce.anisotropic_enabled" \
  >"${RESULT_DIR}/proxemic_anisotropic_enabled.txt"
container_bash "${ROS_SETUP} && ros2 param get /controller_server FollowPath.ProxemicForce.front_scale" \
  >"${RESULT_DIR}/proxemic_front_scale.txt"
container_bash "${ROS_SETUP} && ros2 param get /controller_server FollowPath.ProxemicForce.side_scale" \
  >"${RESULT_DIR}/proxemic_side_scale.txt"
container_bash "${ROS_SETUP} && ros2 param get /controller_server FollowPath.ProxemicForce.back_scale" \
  >"${RESULT_DIR}/proxemic_back_scale.txt"
container_bash "${ROS_SETUP} && timeout 10 ros2 topic echo /people --once" \
  >"${RESULT_DIR}/people.yaml"

start_process transcription_status.txt \
  "env PYTHONUNBUFFERED=1 timeout 1800 ros2 topic echo /museum/transcription_status --field data" \
  transcription_status_capture
start_process user_text.txt \
  "env PYTHONUNBUFFERED=1 timeout 1800 ros2 topic echo /museum/user_text --field data" \
  user_text_capture
start_process user_request.txt \
  "env PYTHONUNBUFFERED=1 timeout 1800 ros2 topic echo /museum/user_request --field data" \
  user_request_capture
start_process assistant_response.txt \
  "env PYTHONUNBUFFERED=1 timeout 1800 ros2 topic echo /museum/assistant_response --field data" \
  assistant_response_capture
start_process route_request.txt \
  "env PYTHONUNBUFFERED=1 timeout 1800 ros2 topic echo /museum/supplied_route_request --field data" \
  route_request_capture
start_process navigation_result.txt \
  "env PYTHONUNBUFFERED=1 timeout 1800 ros2 topic echo /museum/navigation_result --field data" \
  navigation_result_capture
start_process escort_state.txt \
  "env PYTHONUNBUFFERED=1 timeout 1800 ros2 topic echo /museum/escort_state --field data" \
  escort_state_capture
start_process cmd_vel.yaml \
  "env PYTHONUNBUFFERED=1 timeout 1800 ros2 topic echo /mobile_base_controller/cmd_vel_out" \
  cmd_vel_capture
sleep 2

echo "Running the single real-WAV north_gallery acceptance episode..."
FAILURE_STAGE="experiment"
EXPERIMENT_STARTED=true
set +e
docker exec "${CONTAINER_NAME}" bash -lc "${ROS_SETUP} \
  && timeout --signal=INT --kill-after=20 1800 \
  python3 /root/exchange/scripts/run_supplied_museum_reasoning_episode.py \
    --request-id text_1 --session-id session_1 --style impressionism \
    --audio-file ${CONTAINER_AUDIO} \
    --expected-room impressionism_hall \
    --expected-route north_gallery --expected-candidate candidate_north \
    --expected-escort-sequence escorting waiting escorting arrived \
    --expected-navigation-sequence accepted \
      intentionally_canceled_for_escort_wait accepted succeeded \
    --output ${CONTAINER_RESULT_DIR}/episode.json --timeout 1500" \
  >"${RESULT_DIR}/episode_probe.log" 2>&1 &
PROBE_HOST_PID=$!
set -e

ACTION_CAPTURED=false
for _attempt in $(seq 1 3600); do
  container_bash "${ROS_SETUP} && ros2 action info /navigate_to_pose -t" \
    >"${RESULT_DIR}/navigate_to_pose_action.tmp" 2>/dev/null || true
  container_bash "${ROS_SETUP} && ros2 action info /navigate_through_poses -t" \
    >"${RESULT_DIR}/navigate_through_poses_action.tmp" 2>/dev/null || true
  if grep -q 'supplied_museum_route_runner' "${RESULT_DIR}/navigate_to_pose_action.tmp" \
    && grep -q 'supplied_museum_route_runner' "${RESULT_DIR}/navigate_through_poses_action.tmp"; then
    container_bash "${ROS_SETUP} && ros2 node list" \
      >"${RESULT_DIR}/node_list.tmp" 2>/dev/null || true
  fi
  if grep -Fxq '/supplied_museum_route_runner' "${RESULT_DIR}/node_list.tmp" 2>/dev/null \
    && grep -Fxq '/supplied_museum_route_request_bridge' "${RESULT_DIR}/node_list.tmp" 2>/dev/null; then
    mv -- "${RESULT_DIR}/navigate_to_pose_action.tmp" \
      "${RESULT_DIR}/navigate_to_pose_action.txt"
    mv -- "${RESULT_DIR}/navigate_through_poses_action.tmp" \
      "${RESULT_DIR}/navigate_through_poses_action.txt"
    mv -- "${RESULT_DIR}/node_list.tmp" "${RESULT_DIR}/node_list.txt"
    container_bash "${ROS_SETUP} && ros2 action info /navigate_to_pose -v" \
      >"${RESULT_DIR}/navigate_to_pose_action_verbose_raw.txt" 2>&1 || true
    container_bash "${ROS_SETUP} && ros2 action info /navigate_through_poses -v" \
      >"${RESULT_DIR}/navigate_through_poses_action_verbose_raw.txt" 2>&1 || true
    : >"${RESULT_DIR}/route_subsystem_node_info.txt"
    while IFS= read -r route_node; do
      case "${route_node}" in
        /supplied_museum_route_runner|/supplied_museum_route_request_bridge)
          printf '\n=== %s ===\n' "${route_node}" \
            >>"${RESULT_DIR}/route_subsystem_node_info.txt"
          container_bash "${ROS_SETUP} && ros2 node info ${route_node}" \
            >>"${RESULT_DIR}/route_subsystem_node_info.txt" 2>&1
          ;;
      esac
    done <"${RESULT_DIR}/node_list.txt"
    ACTION_CAPTURED=true
    break
  fi
  kill -0 "${PROBE_HOST_PID}" 2>/dev/null || break
  sleep 0.25
done

set +e
wait "${PROBE_HOST_PID}"
PROBE_STATUS=$?
set -e
if [[ ${PROBE_STATUS} -ne 0 && ! -f "${RESULT_DIR}/episode.json" ]]; then
  die "The end-to-end episode probe failed before producing episode.json; see episode_probe.log."
fi
[[ "${ACTION_CAPTURED}" == true ]] \
  || die "Could not capture the active supplied route subsystem ownership evidence."

sleep 2
container_bash "${ROS_SETUP} && timeout 10 ros2 topic echo /gazebo/model_states --once" \
  >"${RESULT_DIR}/final_gazebo_pose.yaml"
container_bash "${ROS_SETUP} && timeout 10 ros2 topic echo /museum/ground_truth_odom --once" \
  >"${RESULT_DIR}/final_ground_truth_odom.yaml"
container_bash "${ROS_SETUP} && timeout 10 ros2 topic echo /amcl_pose --once" \
  >"${RESULT_DIR}/final_amcl_pose.yaml"
container_bash "${ROS_SETUP} && timeout 10 ros2 topic echo /mobile_base_controller/cmd_vel_out --once" \
  >"${RESULT_DIR}/final_cmd_vel.yaml"

for index in $(seq 1 $((${#ROS_PIDS[@]} - 1))); do
  stop_process_group "${ROS_PIDS[index]}" || true
done
sleep 1

docker exec -i "${CONTAINER_NAME}" python3 - \
  "${CONTAINER_RESULT_DIR}" "${EXPECTED_TEXT}" "${TEST_SUMMARY}" \
  "${TRIAL}" "$(git -C "${REPO_ROOT}" rev-parse HEAD)" <<'PY'
import json
import math
from pathlib import Path
import re
import sys
import unicodedata

import yaml


root = Path(sys.argv[1])
expected_text = sys.argv[2]
test_summary = sys.argv[3]
trial = int(sys.argv[4])
git_commit = sys.argv[5]


def read(name):
    return (root / name).read_text(encoding="utf-8")


def json_lines(name):
    return [
        json.loads(line)
        for line in read(name).splitlines()
        if line.strip().startswith("{")
    ]


def yaml_documents(name):
    return [item for item in yaml.safe_load_all(read(name)) if isinstance(item, dict)]


def normalize(text):
    value = unicodedata.normalize("NFKD", text).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def position(document, prefix):
    current = document
    for key in prefix:
        current = current[key]
    return {"x": float(current["x"]), "y": float(current["y"])}


episode = json.loads(read("episode.json"))
engagement_records = [
    json.loads(line)
    for line in read("engagement_records.jsonl").splitlines()
    if line.strip()
]
engagement_payloads = [
    record["payload"]
    for record in engagement_records
    if isinstance(record.get("payload"), dict)
]
engagement_sequence = []
for payload in engagement_payloads:
    state = str(payload.get("state", "")).upper()
    if state and (not engagement_sequence or engagement_sequence[-1] != state):
        engagement_sequence.append(state)

def is_subsequence(expected, observed):
    iterator = iter(observed)
    return all(any(item == wanted for item in iterator) for wanted in expected)

first_person_record = next(
    (
        record for record in engagement_records
        if isinstance(record.get("payload"), dict)
        and record["payload"].get("person_detected") is True
    ),
    None,
)
engaged_record = next(
    (
        record for record in engagement_records
        if isinstance(record.get("payload"), dict)
        and str(record["payload"].get("state", "")).lower() == "engaged"
    ),
    None,
)
engagement_latency = (
    engaged_record["received_monotonic_s"]
    - first_person_record["received_monotonic_s"]
    if first_person_record is not None and engaged_record is not None
    else None
)
engaged_payload = engaged_record["payload"] if engaged_record else {}
statuses = json_lines("transcription_status.txt")
structured = episode["structured_requests"]
routes = episode["route_requests"]
decision = episode["assistant_response"]
navigation = episode["navigation_result"]
transcriptions = episode["transcriptions"]
escort_sequence = [item["state"] for item in episode["escort_states"]]
events = navigation["navigation_events"]
uuids = navigation["goal_uuids"]

session_messages = json_lines("session_state.txt")
gazebo_document = yaml_documents("final_gazebo_pose.yaml")[-1]
ground_truth_document = yaml_documents("final_ground_truth_odom.yaml")[-1]
amcl_document = yaml_documents("final_amcl_pose.yaml")[-1]
cmd_documents = yaml_documents("final_cmd_vel.yaml")
people_document = yaml_documents("people.yaml")[-1]

tiago_index = gazebo_document["name"].index("tiago")
gazebo_position = gazebo_document["pose"][tiago_index]["position"]
gazebo_pose = {
    "x": float(gazebo_position["x"]),
    "y": float(gazebo_position["y"]),
}
ground_truth_pose = position(
    ground_truth_document, ("pose", "pose", "position")
)
amcl_pose = position(amcl_document, ("pose", "pose", "position"))
target = {"x": 0.0, "y": 16.0}
gazebo_error = math.hypot(
    gazebo_pose["x"] - target["x"], gazebo_pose["y"] - target["y"]
)
amcl_error = math.hypot(
    amcl_pose["x"] - target["x"], amcl_pose["y"] - target["y"]
)

last_cmd = cmd_documents[-1]["twist"]
terminal_cmd = {
    "linear_x": float(last_cmd["linear"]["x"]),
    "linear_y": float(last_cmd["linear"]["y"]),
    "linear_z": float(last_cmd["linear"]["z"]),
    "angular_x": float(last_cmd["angular"]["x"]),
    "angular_y": float(last_cmd["angular"]["y"]),
    "angular_z": float(last_cmd["angular"]["z"]),
}
people_ids = [item["identifier"] for item in people_document["pedestrians"]]

controller_plugin = read("controller_plugin.txt")
controller_critics = read("controller_critics.txt")
proxemic_class = read("proxemic_class.txt")
proxemic_people_topic = read("proxemic_people_topic.txt")
proxemic_ignored = read("proxemic_ignored_identifiers.txt")
anisotropic_enabled = read("proxemic_anisotropic_enabled.txt")
front_scale = read("proxemic_front_scale.txt")
side_scale = read("proxemic_side_scale.txt")
back_scale = read("proxemic_back_scale.txt")
launch_log = read("launch.log")
node_list = {
    line.strip()
    for line in read("node_list.txt").splitlines()
    if line.strip().startswith("/")
}
to_pose_action_info = read("navigate_to_pose_action.txt")
through_poses_action_info = read("navigate_through_poses_action.txt")
route_node_info = read("route_subsystem_node_info.txt")
lifecycle = read("lifecycle_states.txt")


def action_clients(action_info):
    clients = []
    in_clients = False
    for line in action_info.splitlines():
        if line.startswith("Action clients:"):
            in_clients = True
            continue
        if line.startswith("Action servers:"):
            break
        if in_clients and line.strip().startswith("/"):
            clients.append(line.strip().split()[0])
    return clients


to_pose_clients = action_clients(to_pose_action_info)
through_poses_clients = action_clients(through_poses_action_info)
route_subsystem_nodes = {
    node
    for node in node_list
    if node.startswith("/supplied_museum_route")
}
known_museum_nodes = {
    "/reasoning_node",
    "/language_node",
    "/speech_to_text_node",
    "/semantic_graph_node",
    "/semantic_navigation_node",
    "/semantic_route_dispatcher",
    "/supplied_museum_route_runner",
    "/supplied_museum_route_request_bridge",
    "/visitor_session_node",
    "/scripted_visitor_node",
    "/simulated_people_node",
}
concurrent_museum_clients = (
    (set(to_pose_clients) | set(through_poses_clients))
    & known_museum_nodes
) - {"/supplied_museum_route_runner"}
ownership_proven = (
    "/semantic_navigation_node" not in node_list
    and route_subsystem_nodes
    == {
        "/supplied_museum_route_runner",
        "/supplied_museum_route_request_bridge",
    }
    and to_pose_clients.count("/supplied_museum_route_runner") == 1
    and through_poses_clients.count("/supplied_museum_route_runner") == 1
    and not concurrent_museum_clients
    and "=== /supplied_museum_route_runner ===" in route_node_info
    and "=== /supplied_museum_route_request_bridge ===" in route_node_info
)

succeeded_waypoints = [
    event["waypoint"] for event in events if event["status"] == "succeeded"
]
assertions = {
    "00_engagement_rgb_lidar_sequence": (
        is_subsequence(
            ["PASSING", "POTENTIAL_INTERACTION", "ENGAGED"],
            engagement_sequence,
        )
        and engaged_payload.get("person_detected") is True
        and engaged_payload.get("distance_m") is not None
        and engaged_payload.get("bearing_rad") is not None
    ),
    "01_single_successful_stt": len(statuses) == 1 and statuses[0].get("status") == "success",
    "02_single_correct_user_text": len(transcriptions) == 1 and normalize(transcriptions[0]) == normalize(expected_text),
    "03_single_structured_request": len(structured) == 1,
    "04_request_linked_to_active_session": len(session_messages) == 1 and session_messages[0].get("state") == "active" and len(structured) == 1 and structured[0].get("session_id") == session_messages[0].get("session_id") == "session_1",
    "05_reasoning_selected_impressionism": isinstance(decision, dict) and decision.get("selected_room") == "impressionism_hall" and decision.get("status") == "success",
    "06_single_north_gallery_route": len(routes) == 1 and routes[0].get("route") == "north_gallery",
    "07_reasoning_not_bypassed": isinstance(decision, dict) and decision.get("request_id") == structured[0].get("request_id") == routes[0].get("request_id"),
    "08_unique_nav2_owner": ownership_proven,
    "09_escort_sequence": escort_sequence == ["escorting", "waiting", "escorting", "arrived"],
    "10_waiting_canceled_goal": [item["status"] for item in events] == ["accepted", "intentionally_canceled_for_escort_wait", "accepted", "succeeded"],
    "11_resume_new_unique_uuid": len(uuids) == 2 and len(set(uuids)) == 2 and events[0]["goal_uuid"] != events[2]["goal_uuid"],
    "12_completed_waypoint_not_repeated": succeeded_waypoints == ["candidate_north"],
    "13_nav2_succeeded": navigation.get("status") == "succeeded" and navigation.get("nav2_succeeded") is True,
    "14_candidate_north_reached": navigation.get("final_candidate") == "candidate_north" and navigation.get("candidate_reached") is True,
    "15_amcl_active": lifecycle.count("active") == 6 and math.isfinite(amcl_error),
    "16_dwb_active": "dwb_core::DWBLocalPlanner" in controller_plugin,
    "17_proxemic_force_active": "ProxemicForce" in controller_critics and "museum_social_critic::ProxemicForceCritic" in proxemic_class and "ProxemicForceCritic subscribed to /people" in launch_log,
    "17b_anisotropic_critic_active": (
        "Boolean value is: True" in anisotropic_enabled
        and "Double value is: 1.4" in front_scale
        and "Double value is: 1.0" in side_scale
        and "Double value is: 0.8" in back_scale
    ),
    "18_people_received": bool(people_ids) and bool(re.search(r"Received [1-9][0-9]* pedestrians on /people", launch_log)),
    "19_visitor_ignored": "visitor_1" in proxemic_ignored and "/people" in proxemic_people_topic and bool(re.search(r"ignored=[1-9][0-9]*", launch_log)),
    "20_terminal_cmd_vel_zero": bool(cmd_documents) and all(abs(value) <= 1.0e-6 for value in terminal_cmd.values()),
    "21_gazebo_target_error_below_0_5_m": gazebo_error < 0.5 and navigation.get("gazebo_target_error_m", math.inf) < 0.5,
}

test_match = re.search(
    r"Summary: (\d+) tests, (\d+) errors, (\d+) failures, (\d+) skipped",
    test_summary,
)
report = {
    "benchmark": "end_to_end",
    "run_id": f"end-to-end-{trial}",
    "trial": trial,
    "campaign_git_commit": git_commit,
    "scenario": "audio_impressionism_north_gallery",
    "variant": "groq_whisper_anisotropic_engagement_required",
    "configuration": "engagement_required_groq_stt_anisotropic",
    "status": "passed" if all(assertions.values()) else "failed",
    "failure_reason": None if all(assertions.values()) else "One or more final E2E assertions failed.",
    "overall_success": all(assertions.values()),
    "engagement_success": assertions["00_engagement_rgb_lidar_sequence"],
    "engagement_sequence": engagement_sequence,
    "engagement_activation_latency_s": engagement_latency,
    "person_detected": engaged_payload.get("person_detected"),
    "person_confidence": engaged_payload.get("person_confidence"),
    "lidar_distance_m": engaged_payload.get("distance_m"),
    "lidar_bearing_rad": engaged_payload.get("bearing_rad"),
    "wav_to_transcript": {
        "audio_basename": "request.wav",
        "status": statuses[0] if statuses else None,
        "transcript": transcriptions[0] if transcriptions else None,
    },
    "structured_request": structured[0] if len(structured) == 1 else structured,
    "session_id": structured[0].get("session_id") if len(structured) == 1 else None,
    "visitor_id": session_messages[0].get("track_id") if session_messages else None,
    "stt_success": len(statuses) == 1 and statuses[0].get("status") == "success",
    "stt_latency_s": statuses[0].get("latency_seconds") if statuses else None,
    "transcript": transcriptions[0] if len(transcriptions) == 1 else None,
    "transcript_correct": len(transcriptions) == 1 and normalize(transcriptions[0]) == normalize(expected_text),
    "structured_request_count": len(structured),
    "session_correlation": assertions["04_request_linked_to_active_session"],
    "intent_correct": len(structured) == 1 and structured[0].get("intent") == "recommend_and_prepare_navigation",
    "constraints_correct": len(structured) == 1 and structured[0].get("constraints") == {"style": "impressionism"},
    "reasoning_result": decision,
    "route_request": routes[0] if len(routes) == 1 else routes,
    "escort_sequence": escort_sequence,
    "navigation_sequence": [item["status"] for item in events],
    "goal_uuids": uuids,
    "ownership_evidence": {
        "active_route_subsystem_nodes": sorted(route_subsystem_nodes),
        "navigate_to_pose_clients": to_pose_clients,
        "navigate_through_poses_clients": through_poses_clients,
        "concurrent_museum_clients": sorted(concurrent_museum_clients),
        "semantic_navigation_node_active": (
            "/semantic_navigation_node" in node_list
        ),
        "verbose_raw_note": (
            "ROS 2 Humble action info has no -v option; raw CLI outputs are "
            "preserved and -t output is used for structured evidence."
        ),
    },
    "gazebo_pose": gazebo_pose,
    "gazebo_target_error_m": gazebo_error,
    "ground_truth_odom_pose": ground_truth_pose,
    "amcl_pose": amcl_pose,
    "amcl_target_error_m": amcl_error,
    "dwb_status": controller_plugin.strip(),
    "proxemic_force_status": {
        "class": proxemic_class.strip(),
        "received_people_log": bool(re.search(r"Received [1-9][0-9]* pedestrians on /people", launch_log)),
        "ignored_visitor_log": bool(re.search(r"ignored=[1-9][0-9]*", launch_log)),
    },
    "anisotropic_critic_active": assertions["17b_anisotropic_critic_active"],
    "people_stream_received": assertions["18_people_received"],
    "escort_arrived": bool(escort_sequence) and escort_sequence[-1] == "arrived",
    "nav_success": assertions["13_nav2_succeeded"],
    "dwb_active": assertions["16_dwb_active"],
    "proxemic_force_active": assertions["17_proxemic_force_active"],
    "terminal_cmd_vel_zero": assertions["20_terminal_cmd_vel_zero"],
    "people_identifiers": people_ids,
    "terminal_cmd_vel": terminal_cmd,
    "test_totals": {
        "tests": int(test_match.group(1)),
        "errors": int(test_match.group(2)),
        "failures": int(test_match.group(3)),
        "skipped": int(test_match.group(4)),
    } if test_match else None,
    "assertions": assertions,
}
(root.parent / f"trial_{trial}.json").write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(root / "final_report.json").write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(json.dumps(report, indent=2, sort_keys=True))
raise SystemExit(0 if report["status"] == "passed" else 3)
PY

echo
echo "FINAL STATUS: PASS"
echo "Report: ${RESULT_DIR}/final_report.json"
