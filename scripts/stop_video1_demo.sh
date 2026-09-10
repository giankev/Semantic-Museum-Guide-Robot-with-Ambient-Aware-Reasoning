#!/usr/bin/env bash
set -euo pipefail

CONTAINER="museum_tiago"
STATE_DIR="/tmp/tiago_video1_demo_${UID}"

stop_recorded_process() {
  local name="$1"
  local pid_file="${STATE_DIR}/${name}.pid"
  [[ -f "${pid_file}" ]] || return
  local pid command
  pid="$(<"${pid_file}")"
  if [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null; then
    command="$(tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null || true)"
    if [[ "${command}" == *"docker"*"${CONTAINER}"* ]]; then
      kill -INT "${pid}" 2>/dev/null || true
    fi
  fi
}

for helper in control monitor rviz visualizer crowd simulation; do
  stop_recorded_process "${helper}"
done

sleep 2
for helper in control monitor rviz visualizer crowd simulation; do
  pid_file="${STATE_DIR}/${helper}.pid"
  [[ -f "${pid_file}" ]] || continue
  pid="$(<"${pid_file}")"
  if [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null; then
    command="$(tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null || true)"
    if [[ "${command}" == *"docker"*"${CONTAINER}"* ]]; then
      kill -TERM "${pid}" 2>/dev/null || true
    fi
  fi
done

if [[ -f "${STATE_DIR}/container_started" ]] \
  && [[ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null || true)" == "true" ]]; then
  docker stop --timeout 10 "${CONTAINER}" >/dev/null
fi

for state_file in "${STATE_DIR}"/*.pid "${STATE_DIR}"/*.log "${STATE_DIR}/container_started"; do
  [[ -e "${state_file}" ]] && rm -f "${state_file}"
done
rmdir "${STATE_DIR}" 2>/dev/null || true

echo "Video 1 demo helpers stopped."
