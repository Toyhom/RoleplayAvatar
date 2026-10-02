#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$PROJECT_ROOT/.local.env" ]]; then
  set -a
  source "$PROJECT_ROOT/.local.env"
  set +a
fi
PYTHON="${AVATAR_ENV_PREFIX:+$AVATAR_ENV_PREFIX/bin/python}"
PYTHON="${PYTHON:-$(command -v python)}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing Python interpreter: $PYTHON" >&2
  exit 1
fi
export AVATAR_PROJECT_ROOT="$PROJECT_ROOT"
export PIP_CACHE_DIR="$PROJECT_ROOT/.cache/pip"
export XDG_CACHE_HOME="$PROJECT_ROOT/.cache/xdg"
export TMPDIR="$PROJECT_ROOT/.cache/tmp"
mkdir -p "$TMPDIR"
cd "$PROJECT_ROOT"
