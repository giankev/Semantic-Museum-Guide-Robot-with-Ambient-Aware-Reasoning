#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COUNT=8
OPTIONS=()
while (($#)); do
  case "$1" in
    --actors) COUNT="${2:?--actors requires a count}"; shift 2 ;;
    --headless|--runtime-audit|--observe-only) OPTIONS+=("$1"); shift ;;
    --help|-h) echo "Usage: $0 [--actors 1|3|6|8] [--headless] [--runtime-audit] [--observe-only]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ "${COUNT}" =~ ^(1|3|6|8)$ ]] || { echo 'Supported stages: 1, 3, 6, 8' >&2; exit 2; }
export VIDEO1_ACTOR_COUNT="${COUNT}" VIDEO1_SOCIAL_YIELD=true
export VIDEO1_SERVER_RENDERER="${VIDEO1_SERVER_RENDERER:-software}"
exec "${ROOT}/scripts/start_video1_animated_demo.sh" "${OPTIONS[@]}"
