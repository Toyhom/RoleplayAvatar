#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
: "${GPUQ_JOB_ID:?This entrypoint must run inside GPUQ}"
: "${AVATAR_MODEL_ROOT:?Set the shared model directory in .local.env}"
export HF_HOME="$PROJECT_ROOT/.cache/huggingface"
unset TRANSFORMERS_CACHE
export TORCH_HOME="$PROJECT_ROOT/.cache/torch"
export AVATAR_RUN_DIR="$PROJECT_ROOT/outputs/${GPUQ_NODE}/${GPUQ_JOB_ID}"
mkdir -p "$AVATAR_RUN_DIR"
exec "$@"
