#!/usr/bin/env bash
# Install into a new, explicitly chosen prefix. Never mutates an unrelated environment.
set -euo pipefail
if [[ $# != 3 ]]; then
  echo 'Usage: bash scripts/install_model_env.sh vision|asset|qwen|cosyvoice|face|audio2face|portrait|vllm|sglang|faster-whisper /absolute/python /absolute/new-prefix' >&2
  exit 2
fi
kind="$1"; base_python="$2"; prefix="$3"
case "$kind" in vision|asset|qwen|cosyvoice|face|audio2face|portrait|vllm|sglang|faster-whisper) ;; *) exit 2 ;; esac
[[ "$prefix" == /* && "$base_python" == /* && -x "$base_python" ]] || exit 2
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project"
if [[ -e "$prefix" ]]; then
  [[ -f "$prefix/.roleplay-avatar-env" && "$(cat "$prefix/.roleplay-avatar-env")" == "$kind" ]] || {
    echo 'Existing environment is not owned by this installer; preserved.' >&2; exit 1;
  }
else
  "$base_python" -m venv "$prefix"
  echo "$kind" > "$prefix/.roleplay-avatar-env"
fi
python="$prefix/bin/python"
export PIP_CACHE_DIR="$project/.cache/pip"
export TMPDIR="$project/.cache/tmp"
mkdir -p "$TMPDIR"
"$python" -m pip install 'pip==25.3' 'setuptools==79.0.1' wheel packaging ninja
if [[ "$kind" == vllm || "$kind" == sglang || "$kind" == faster-whisper ]]; then
  "$python" -m pip install -r "requirements/$kind.txt"
  if [[ "$kind" == vllm ]]; then
    "$python" -m pip install -e "$project"
  fi
elif [[ "$kind" == face ]]; then
  "$python" -m pip install -r requirements/face.txt
  "$python" -m pip install mediapipe==0.10.21 --no-deps
elif [[ "$kind" == portrait ]]; then
  "$python" -m pip install -r requirements/portrait.txt
elif [[ "$kind" == cosyvoice ]]; then
  "$python" -m pip install torch==2.3.1 torchaudio==2.3.1 torchvision==0.18.1 --index-url https://download.pytorch.org/whl/cu121
  "$python" -m pip install -r requirements/cosyvoice.txt
  "$python" -m pip install openai-whisper==20231117 pyworld==0.3.4 wget==3.2 --no-build-isolation
else
  "$python" -m pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu126
  case "$kind" in
    audio2face) "$python" -m pip install -r requirements/audio-face.txt ;;
    vision) "$python" -m pip install -r requirements/vision.txt ;;
    qwen) "$python" -m pip install ./third_party/qwen3_tts 'gradio==5.49.1' 'librosa==0.11.0' 'onnxruntime==1.23.2' ;;
    asset)
      : "${CUDA_HOME:?Set CUDA_HOME to the CUDA 12.6 toolkit before building extensions}"
      "$python" -m pip install -r requirements/asset.txt
      "$python" -m pip install ./third_party/utils3d ./third_party/pytorch3d ./third_party/nvdiffrast --no-build-isolation
      "$python" -m pip install flash-attn==2.8.3 --no-build-isolation
      ;;
  esac
fi
"$python" -m pip freeze > "$prefix/.roleplay-avatar-installed.txt"
echo "Installed $kind at $prefix. Run its GPU witness before starting model inference."
