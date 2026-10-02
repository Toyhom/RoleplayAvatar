#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
if [[ "$(id -u)" == 0 ]]; then
  echo "Submit under the project owner's account (see guides/setup.md)." >&2
  exit 1
fi
if [[ $# -lt 1 || "$1" != /* || ! -x "$1" ]]; then
  echo "Usage: bash scripts/submit_gpu.sh /absolute/environment/bin/python script.py [args...]" >&2
  exit 2
fi
exec gpuq submit --node "${AVATAR_NODE:-auto}" --name "${AVATAR_JOB_NAME:-roleplay-avatar}" --gpus "${AVATAR_GPUS:-1}" -- bash "$PROJECT_ROOT/scripts/gpu_worker.sh" "$@"
