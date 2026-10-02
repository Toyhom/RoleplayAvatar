#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
if [[ "${AVATAR_CREATION_RUNNER:-}" == "gpuq" ]]; then
  : "${GPUQ_JOB_ID:?Character generation on this deployment must run through GPUQ}"
fi
export AVATAR_FACE_PYTHON AVATAR_VISION_PYTHON AVATAR_PORTRAIT_PYTHON AVATAR_ASSET_PYTHON AVATAR_QWEN_PYTHON AVATAR_MODEL_ROOT
export HF_HOME="$PROJECT_ROOT/.cache/huggingface"
export TORCH_HOME="$PROJECT_ROOT/.cache/torch"
export U2NET_HOME="$AVATAR_MODEL_ROOT/rembg"
export ATTN_BACKEND=sdpa SPARSE_ATTN_BACKEND=flash_attn
creation_script="services/create_character.py"
if [[ "$($PYTHON -c 'import json,sys; print(json.load(open(sys.argv[1]+"/request.json")).get("source","image"))' "$1")" == "live2d" ]]; then
  creation_script="services/import_live2d.py"
fi
exec "$PYTHON" "$creation_script" "$@"
