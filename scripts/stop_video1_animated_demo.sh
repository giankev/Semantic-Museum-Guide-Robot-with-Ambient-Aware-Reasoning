#!/usr/bin/env bash
set -euo pipefail
command -v docker >/dev/null || { echo 'Docker is required on the simulation host.' >&2; exit 1; }
CONTAINER="museum_video1_animated_${UID}"
label="$(docker inspect -f '{{index .Config.Labels "org.museum.video1"}}' "${CONTAINER}" 2>/dev/null || true)"
if [[ "${label}" == animated-poc ]]; then
  container_id="$(docker inspect -f '{{.Id}}' "${CONTAINER}")"
  docker stop --time 10 "${container_id}" >/dev/null
  # --rm deletion can finish after docker stop returns. Wait for that exact
  # container before allowing a staged launcher to reuse its name.
  removal_deadline=$((SECONDS + 15))
  while docker inspect "${container_id}" >/dev/null 2>&1; do
    if ((SECONDS >= removal_deadline)); then
      echo "Stopped ${container_id}, but automatic removal did not finish within 15 seconds." >&2
      exit 1
    fi
    sleep 0.1
  done
  echo 'Animated POC stopped; logs retained. The museum_tiago fallback container is untouched.'
elif [[ -z "${label}" ]]; then
  echo 'No owned animated POC is running.'
else
  echo "Refusing to stop ${CONTAINER}: ownership label differs." >&2
  exit 1
fi
