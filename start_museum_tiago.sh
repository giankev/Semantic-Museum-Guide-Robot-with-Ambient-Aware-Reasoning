#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

xhost +local:docker >/dev/null 2>&1 || true

GPU_ARGS=()
RENDER_ENV=()
GROQ_ENV=()
for variable_name in GROQ_API_KEY GROQ_BASE_URL GROQ_MODEL GROQ_STT_MODEL; do
  if [[ -n "${!variable_name:-}" ]]; then
    GROQ_ENV+=(-e "${variable_name}")
  fi
done

# Prefer real GPU/DRI rendering whenever the host exposes it.  The previous
# fallback forced llvmpipe on every non-NVIDIA machine, which can make Gazebo
# render at only a few FPS even when an Intel/AMD GPU is available through
# /dev/dri.  Software rendering remains the final fallback.
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  echo "Rendering: NVIDIA GPU"
  GPU_ARGS=(--gpus all)
elif [[ -d /dev/dri ]]; then
  echo "Rendering: host DRI device (Intel/AMD hardware acceleration)"
  GPU_ARGS=(--device=/dev/dri:/dev/dri)
  RENDER_ENV=(-e LIBGL_ALWAYS_SOFTWARE=0)
else
  echo "Rendering: software llvmpipe fallback"
  RENDER_ENV=(-e LIBGL_ALWAYS_SOFTWARE=1 -e GALLIUM_DRIVER=llvmpipe)
fi

docker run --rm -it \
  --name museum_tiago \
  --net=host \
  "${GPU_ARGS[@]}" \
  -e DISPLAY="${DISPLAY:-:0}" \
  -e QT_X11_NO_MITSHM=1 \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  "${GROQ_ENV[@]}" \
  "${RENDER_ENV[@]}" \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v "${SCRIPT_DIR}:/root/exchange" \
  -w /root/exchange \
  museum-tiago:humble \
  bash
