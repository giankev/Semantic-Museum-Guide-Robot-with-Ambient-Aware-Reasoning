#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RESULT_DIR="${REPO_ROOT}/.phase8_acceptance_tmp"
CONTAINER_RESULT_DIR="/root/exchange/.phase8_acceptance_tmp"
CONTAINER_NAME="museum_tiago_phase8_acceptance"
IMAGE_NAME="museum-tiago:humble"
WORKSPACE="/root/exchange/exchange/museum_ws"
ROS_DOMAIN_ID="78"
ROS_SETUP="source /opt/ros/humble/setup.bash && source /root/tiago_public_ws/install/setup.bash && source /root/social_nav_ws/install/setup.bash && source ${WORKSPACE}/install/setup.bash && export ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
SUPPORTED_EXTENSIONS=(wav mp3 mp4 mpeg mpga m4a ogg flac webm)
MAX_AUDIO_BYTES=$((25 * 1024 * 1024))

CONTAINER_STARTED=false
ACCEPTANCE_PASSED=false
ROS_PIDS=()
ROS_DESCRIPTIONS=()
LAST_PID=""
COPIED_AUDIO=""

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  set +e

  local index pid description
  if [[ "${CONTAINER_STARTED}" == true ]]; then
    for ((index = ${#ROS_PIDS[@]} - 1; index >= 0; index--)); do
      pid=${ROS_PIDS[index]}
      description=${ROS_DESCRIPTIONS[index]:-"process group ${pid}"}
      stop_process_group "${pid}" "${description}" >/dev/null 2>&1 || true
    done
    docker container rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  fi

  [[ -z "${COPIED_AUDIO}" ]] || rm -f -- "${COPIED_AUDIO}"
  rm -f -- "${RESULT_DIR}/unsupported.txt"
  unset GROQ_API_KEY

  if [[ "${ACCEPTANCE_PASSED}" == true && ${exit_code} -eq 0 ]]; then
    rm -rf -- "${RESULT_DIR}"
    echo "Privacy cleanup: copied audio and temporary acceptance data removed."
  else
    rm -f -- "${RESULT_DIR}/user_text.txt" "${RESULT_DIR}/live_result.json"
    if [[ -d "${RESULT_DIR}" ]]; then
      echo "Acceptance did not pass; non-transcript diagnostics preserved at ${RESULT_DIR}"
    fi
    echo "Privacy cleanup: copied audio and transcript capture removed."
  fi
  exit "${exit_code}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

die() {
  echo "ERROR: $*" >&2
  exit 1
}

container_bash() {
  docker exec "${CONTAINER_NAME}" bash -lc "$1"
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

process_alive() {
  local pid=${1:-}
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  container_bash "ps -eo pgid=,stat= | awk -v target='${pid}' \
    '\$1 == target && \$2 !~ /^Z/ { found=1 } \
    END { exit(found ? 0 : 1) }'" >/dev/null 2>&1
}

stop_process_group() {
  local pid=${1:-}
  local description=${2:-process}
  local attempt
  if ! process_alive "${pid}"; then
    return 0
  fi
  container_bash "kill -TERM -- -${pid} >/dev/null 2>&1 || true" || true
  for attempt in {1..20}; do
    process_alive "${pid}" || return 0
    sleep 0.25
  done
  container_bash "kill -KILL -- -${pid} >/dev/null 2>&1 || true" || true
  for attempt in {1..8}; do
    process_alive "${pid}" || return 0
    sleep 0.25
  done
  die "${description} did not stop."
}

json_count() {
  local file=$1
  [[ -f "${file}" ]] || { echo 0; return; }
  grep -c '^{' "${file}" 2>/dev/null || true
}

text_count() {
  local file=$1
  [[ -f "${file}" ]] || { echo 0; return; }
  awk 'NF && $0 != "---" { count++ } END { print count + 0 }' "${file}"
}

wait_for_count() {
  local count_function=$1
  local file=$2
  local expected=$3
  local timeout_seconds=$4
  local deadline=$((SECONDS + timeout_seconds))
  while ((SECONDS < deadline)); do
    if (( $("${count_function}" "${file}") >= expected )); then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

wait_for_topics() {
  local deadline=$((SECONDS + 20))
  local topics
  local required=(
    /museum/audio_file /museum/transcription_status /museum/user_text
    /museum/user_request /museum/assistant_response /museum/session_state
  )
  while ((SECONDS < deadline)); do
    topics="$(container_bash "${ROS_SETUP} && ros2 topic list" 2>/dev/null || true)"
    local present=true topic
    for topic in "${required[@]}"; do
      grep -Fxq "${topic}" <<<"${topics}" || present=false
    done
    [[ "${present}" == true ]] && return 0
    sleep 0.5
  done
  return 1
}

publish_string() {
  local topic=$1
  local value=$2
  container_bash "${ROS_SETUP} && ros2 topic pub --once \
    ${topic} std_msgs/msg/String \"{data: '${value}'}\"" >/dev/null
}

publish_session() {
  publish_string /museum/session_state \
    '{"session_id":"session_1","state":"active"}'
  sleep 1
}

assert_latest_status() {
  local expected=$1
  python3 - "${RESULT_DIR}/transcription_status.txt" "${expected}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    messages = [json.loads(line) for line in stream if line.startswith("{")]
assert messages, "no transcription status captured"
assert messages[-1]["status"] == sys.argv[2], messages[-1]
PY
}

validate_live_chain() {
  python3 - \
    "${RESULT_DIR}/transcription_status.txt" \
    "${RESULT_DIR}/user_text.txt" \
    "${RESULT_DIR}/user_requests.txt" \
    "${RESULT_DIR}/assistant_responses.txt" \
    "${RESULT_DIR}/language.log" \
    "${RESULT_DIR}/live_result.json" \
    "${AUDIO_BASENAME}" "${AUDIO_EXTENSION}" "${AUDIO_SIZE}" \
    "${AUDIO_DURATION:-}" <<'PY'
import json
import re
import sys
import unicodedata


def json_messages(path):
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.startswith("{")]


def text_messages(path):
    with open(path, encoding="utf-8") as stream:
        return [line.strip() for line in stream if line.strip() and line.strip() != "---"]


statuses = json_messages(sys.argv[1])
texts = text_messages(sys.argv[2])
requests = json_messages(sys.argv[3])
responses = json_messages(sys.argv[4])
assert len(statuses) == 1, statuses
assert len(texts) == 1, texts
assert len(requests) == 1, requests
assert len(responses) == 1, responses
assert statuses[0]["status"] == "success", statuses[0]
assert statuses[0]["model"] == "whisper-large-v3-turbo", statuses[0]

normalized = unicodedata.normalize("NFKD", texts[0]).casefold()
normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())
request = requests[0]
response = responses[0]
assert request["intent"] == "recommend_and_prepare_navigation", request
assert request["constraints"]["style"] == "impressionism", request
assert response["selected_room"] == "impressionism_hall", response
assert response["skill"] == "navigate_to", response
assert response["status"] == "success", response

with open(sys.argv[5], encoding="utf-8") as stream:
    language_log = stream.read()
assert "Groq fallback completed" not in language_log

result = {
    "audio_basename": sys.argv[7],
    "audio_format": sys.argv[8],
    "audio_file_size": int(sys.argv[9]),
    "transcription_model": statuses[0]["model"],
    "transcription_latency_seconds": statuses[0]["latency_seconds"],
    "normalized_transcript": normalized,
    "phase7_parser": "deterministic",
    "user_text_publications": len(texts),
    "structured_request": request,
    "reasoner_result": response,
}
if sys.argv[10]:
    result["audio_duration_seconds"] = float(sys.argv[10])
with open(sys.argv[6], "w", encoding="utf-8") as stream:
    json.dump(result, stream, indent=2, sort_keys=True)
PY
}

if [[ $# -ge 1 ]]; then
  AUDIO_PATH=$1
else
  read -r -p "Path to the Phase 8 audio file: " AUDIO_PATH
fi
[[ -n "${AUDIO_PATH}" ]] || die "Audio path is empty."
[[ -e "${AUDIO_PATH}" ]] || die "Audio file does not exist."
[[ -f "${AUDIO_PATH}" ]] || die "Audio path is not a regular file."
[[ -r "${AUDIO_PATH}" ]] || die "Audio file is not readable."

AUDIO_BASENAME="$(basename -- "${AUDIO_PATH}")"
AUDIO_EXTENSION="${AUDIO_BASENAME##*.}"
AUDIO_EXTENSION="${AUDIO_EXTENSION,,}"
SUPPORTED=false
for extension in "${SUPPORTED_EXTENSIONS[@]}"; do
  [[ "${AUDIO_EXTENSION}" == "${extension}" ]] && SUPPORTED=true
done
[[ "${SUPPORTED}" == true ]] || die "Unsupported audio extension."
AUDIO_SIZE="$(stat -c '%s' -- "${AUDIO_PATH}")"
(( AUDIO_SIZE > 0 )) || die "Audio file is empty."
(( AUDIO_SIZE <= MAX_AUDIO_BYTES )) || die "Audio file exceeds 25 MB."

AUDIO_DURATION="$(python3 - "${AUDIO_PATH}" "${AUDIO_EXTENSION}" <<'PY'
import sys
if sys.argv[2] != "wav":
    raise SystemExit
try:
    import wave
    with wave.open(sys.argv[1], "rb") as audio:
        rate = audio.getframerate()
        if rate:
            print(f"{audio.getnframes() / rate:.3f}")
except (EOFError, OSError, wave.Error):
    pass
PY
)"

if [[ -z "${GROQ_API_KEY:-}" ]]; then
  read -r -s -p "GROQ_API_KEY: " GROQ_API_KEY
  echo
fi
[[ -n "${GROQ_API_KEY:-}" ]] || die "GROQ_API_KEY is required for live acceptance."
export GROQ_API_KEY
export GROQ_BASE_URL="${GROQ_BASE_URL:-https://api.groq.com/openai/v1}"
export GROQ_MODEL="${GROQ_MODEL:-openai/gpt-oss-20b}"
export GROQ_STT_MODEL="${GROQ_STT_MODEL:-whisper-large-v3-turbo}"
[[ "${GROQ_STT_MODEL}" == "whisper-large-v3-turbo" ]] \
  || die "Live acceptance requires GROQ_STT_MODEL=whisper-large-v3-turbo."

rm -rf -- "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"
COPIED_AUDIO="${RESULT_DIR}/phase8_input.${AUDIO_EXTENSION}"
CONTAINER_AUDIO_PATH="${CONTAINER_RESULT_DIR}/phase8_input.${AUDIO_EXTENSION}"

DOCKER_ENV_ARGS=(
  -e GROQ_API_KEY -e GROQ_BASE_URL -e GROQ_MODEL -e GROQ_STT_MODEL
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}"
)
for name in HTTP_PROXY HTTPS_PROXY NO_PROXY ALL_PROXY \
  http_proxy https_proxy no_proxy all_proxy \
  SSL_CERT_FILE REQUESTS_CA_BUNDLE CURL_CA_BUNDLE; do
  [[ -z "${!name:-}" ]] || DOCKER_ENV_ARGS+=(-e "${name}")
done

docker container rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
if [[ "${PHASE8_SKIP_DOCKER_BUILD:-0}" == "1" ]]; then
  docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1 \
    || die "PHASE8_SKIP_DOCKER_BUILD=1 but local image ${IMAGE_NAME} does not exist."
  echo "Reusing local image ${IMAGE_NAME}; Docker build skipped."
else
  echo "Building ${IMAGE_NAME}..."
  docker build -f "${REPO_ROOT}/dockerfiles/Dockerfile.tiago_museum" \
    -t "${IMAGE_NAME}" "${REPO_ROOT}"
fi

cp -- "${AUDIO_PATH}" "${COPIED_AUDIO}"
echo "Starting dedicated headless container..."
CONTAINER_STARTED=true
docker run -d --name "${CONTAINER_NAME}" --init --net=host \
  "${DOCKER_ENV_ARGS[@]}" \
  -v "${REPO_ROOT}:/root/exchange" -w /root/exchange \
  "${IMAGE_NAME}" sleep infinity >/dev/null

echo "Building selected packages..."
container_bash "source /opt/ros/humble/setup.bash \
  && source /root/tiago_public_ws/install/setup.bash \
  && source /root/social_nav_ws/install/setup.bash \
  && cd ${WORKSPACE} \
  && colcon build --symlink-install \
    --packages-select museum_assistant museum_social_critic"

echo "Running selected automated tests..."
container_bash "${ROS_SETUP} && cd ${WORKSPACE} \
  && colcon test --packages-select museum_assistant museum_social_critic"
container_bash "cd ${WORKSPACE} && colcon test-result --verbose" \
  | tee "${RESULT_DIR}/test_summary.txt"
TEST_SUMMARY="$(grep '^Summary:' "${RESULT_DIR}/test_summary.txt" | tail -n 1)"
[[ "${TEST_SUMMARY}" =~ Summary:\ ([0-9]+)\ tests,\ ([0-9]+)\ errors,\ ([0-9]+)\ failures,\ ([0-9]+)\ skipped ]] \
  || die "Could not parse test totals."
TEST_TOTAL=${BASH_REMATCH[1]}
TEST_ERRORS=${BASH_REMATCH[2]}
TEST_FAILURES=${BASH_REMATCH[3]}
TEST_SKIPPED=${BASH_REMATCH[4]}
(( TEST_ERRORS == 0 && TEST_FAILURES == 0 )) || die "Automated tests failed."

echo "Verifying pinned SDK and STT model access..."
container_bash "python3 - <<'PY'
import os
import openai
from openai import OpenAI
assert openai.__version__ == '2.46.0'
client = OpenAI(
    api_key=os.environ['GROQ_API_KEY'],
    base_url=os.environ['GROQ_BASE_URL'],
    timeout=20.0,
    max_retries=0,
)
models = {item.id for item in client.models.list().data}
model = os.environ['GROQ_STT_MODEL']
assert model in models, f'{model} is not listed for this account'
print('OpenAI SDK: 2.46.0')
print('Configured STT model available: PASS')
PY" | tee "${RESULT_DIR}/model_check.log"

echo "Starting speech, language, and reasoning nodes..."
start_process speech_to_text.log \
  "ros2 launch museum_assistant speech_to_text.launch.py" speech_to_text_node
STT_PID=${LAST_PID}
start_process language.log \
  "ros2 launch museum_assistant language.launch.py" language_node
LANGUAGE_PID=${LAST_PID}
start_process reasoning.log \
  "ros2 run museum_assistant reasoning_node" reasoning_node
REASONING_PID=${LAST_PID}
sleep 2
process_alive "${STT_PID}" || die "speech_to_text_node exited during startup."
process_alive "${LANGUAGE_PID}" || die "language_node exited during startup."
process_alive "${REASONING_PID}" || die "reasoning_node exited during startup."
wait_for_topics || die "Required Phase 8 topics did not appear."

start_process transcription_status.txt \
  "env PYTHONUNBUFFERED=1 timeout 180 ros2 topic echo /museum/transcription_status --field data" \
  transcription_status_capture
start_process user_text.txt \
  "env PYTHONUNBUFFERED=1 timeout 180 ros2 topic echo /museum/user_text --field data" \
  user_text_capture
start_process user_requests.txt \
  "env PYTHONUNBUFFERED=1 timeout 180 ros2 topic echo /museum/user_request --field data" \
  user_request_capture
start_process assistant_responses.txt \
  "env PYTHONUNBUFFERED=1 timeout 180 ros2 topic echo /museum/assistant_response --field data" \
  assistant_response_capture
sleep 1
publish_session

echo "Running live file-based transcription chain..."
publish_string /museum/audio_file "${CONTAINER_AUDIO_PATH}"
wait_for_count json_count "${RESULT_DIR}/transcription_status.txt" 1 30 \
  || die "No live transcription status was captured."
wait_for_count text_count "${RESULT_DIR}/user_text.txt" 1 10 \
  || die "No /museum/user_text publication was captured."
wait_for_count json_count "${RESULT_DIR}/user_requests.txt" 1 10 \
  || die "No StructuredRequest was captured."
wait_for_count json_count "${RESULT_DIR}/assistant_responses.txt" 1 10 \
  || die "No reasoner response was captured."
sleep 2
validate_live_chain

echo "Running nonexistent-path negative test..."
TEXTS_BEFORE=$(text_count "${RESULT_DIR}/user_text.txt")
publish_string /museum/audio_file "${CONTAINER_RESULT_DIR}/missing.wav"
wait_for_count json_count "${RESULT_DIR}/transcription_status.txt" 2 10 \
  || die "Missing-file status was not captured."
assert_latest_status file_not_found
(( $(text_count "${RESULT_DIR}/user_text.txt") == TEXTS_BEFORE )) \
  || die "Missing file unexpectedly published text."
process_alive "${STT_PID}" || die "STT node exited after missing file."

echo "Running unsupported-format negative test..."
printf '%s\n' "Phase 8 non-audio validation fixture" > "${RESULT_DIR}/unsupported.txt"
publish_string /museum/audio_file "${CONTAINER_RESULT_DIR}/unsupported.txt"
wait_for_count json_count "${RESULT_DIR}/transcription_status.txt" 3 10 \
  || die "Unsupported-format status was not captured."
assert_latest_status unsupported_audio_format
(( $(text_count "${RESULT_DIR}/user_text.txt") == TEXTS_BEFORE )) \
  || die "Unsupported file unexpectedly published text."
process_alive "${STT_PID}" || die "STT node exited after unsupported file."

echo "Running missing-key behavior test..."
stop_process_group "${STT_PID}" speech_to_text_node
start_process speech_to_text_no_key.log \
  "env -u GROQ_API_KEY ros2 launch museum_assistant speech_to_text.launch.py" \
  no_key_speech_to_text_node
NO_KEY_STT_PID=${LAST_PID}
sleep 2
process_alive "${NO_KEY_STT_PID}" || die "No-key STT node failed to start."
publish_string /museum/audio_file "${CONTAINER_AUDIO_PATH}"
wait_for_count json_count "${RESULT_DIR}/transcription_status.txt" 4 10 \
  || die "Missing-key status was not captured."
assert_latest_status missing_api_key
(( $(text_count "${RESULT_DIR}/user_text.txt") == TEXTS_BEFORE )) \
  || die "No-key input unexpectedly published text."
process_alive "${NO_KEY_STT_PID}" || die "No-key STT node exited."

ACCEPTANCE_PASSED=true
echo
echo "Phase 8 live acceptance: PASS"
echo "Phase 8 runtime-validated bounded file-based speech-to-text prototype"
echo "Audio basename: ${AUDIO_BASENAME}"
echo "Audio format: ${AUDIO_EXTENSION}"
echo "Audio file size: ${AUDIO_SIZE} bytes"
[[ -z "${AUDIO_DURATION}" ]] || echo "Audio duration: ${AUDIO_DURATION} seconds"
echo "Tests: ${TEST_TOTAL}; errors: ${TEST_ERRORS}; failures: ${TEST_FAILURES}; skipped: ${TEST_SKIPPED}"
python3 - "${RESULT_DIR}/live_result.json" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as stream:
    result = json.load(stream)
print("Transcription model:", result["transcription_model"])
print("Transcription latency seconds:", result["transcription_latency_seconds"])
print("Normalized transcript:", result["normalized_transcript"])
print("/museum/user_text publications:", result["user_text_publications"])
print("Phase 7 parser:", result["phase7_parser"])
print("StructuredRequest:", json.dumps(result["structured_request"], sort_keys=True))
print("Reasoner result:", json.dumps(result["reasoner_result"], sort_keys=True))
PY
echo "Invalid file behavior: PASS"
echo "Unsupported format behavior: PASS"
echo "Missing-key behavior: PASS"
echo "Gazebo, Nav2, escort, people, and social navigation: not started"
echo "Microphone streaming and TTS: not started"
