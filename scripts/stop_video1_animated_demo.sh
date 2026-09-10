#!/usr/bin/env bash
set -euo pipefail
command -v docker >/dev/null || { echo 'Docker is required on the simulation host.' >&2; exit 1; }
CONTAINER="museum_video1_animated_${UID}"
label="$(docker inspect -f '{{index .Config.Labels "org.museum.video1"}}' "${CONTAINER}" 2>/dev/null || true)"
if [[ "${label}" == animated-poc ]]; then
  docker stop --time 10 "${CONTAINER}" >/dev/null
  echo 'Animated POC stopped; logs retained. The museum_tiago fallback container is untouched.'
elif [[ -z "${label}" ]]; then
  echo 'No owned animated POC is running.'
else
  echo "Refusing to stop ${CONTAINER}: ownership label differs." >&2
  exit 1
fi
