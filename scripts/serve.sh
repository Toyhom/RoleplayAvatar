#!/usr/bin/env bash
set -euo pipefail
requested_port="${AVATAR_PORT:-}"
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
exec "$PYTHON" -m uvicorn roleplay_avatar.app:create_app --factory --host "${AVATAR_HOST:-127.0.0.1}" --port "${requested_port:-${AVATAR_PORT:-18080}}" --ws-max-size 16384
