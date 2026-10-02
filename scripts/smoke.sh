#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
"$PYTHON" -m pip check
"$PYTHON" -m roleplay_avatar.cli validate
"$PYTHON" -m pytest -q
"$PYTHON" -m roleplay_avatar.cli replay
