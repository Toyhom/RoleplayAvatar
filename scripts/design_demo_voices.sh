#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
: "${GPUQ_JOB_ID:?Submit demo voice generation through GPUQ}"
model_path="$($PYTHON -c 'from roleplay_avatar.models import model_path; print(model_path("voice_design", check=True))')"
for sample in sample_haru sample_hiyori sample_robot; do
  if [[ ! -f "outputs/demo-imports/$sample/voice/candidates.json" ]]; then
    "$AVATAR_QWEN_PYTHON" services/character_voices.py --model "$model_path" --job "outputs/demo-imports/$sample"
  fi
done
