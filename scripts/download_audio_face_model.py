"""Download the official-release audio-face checkpoint and verify its recorded local hash."""

import hashlib
import json
import os
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
entry = json.loads((root / "configs/audio-face-model.lock.json").read_text())
target = Path(os.environ["AVATAR_MODEL_ROOT"]) / entry["relative_path"]
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]:
    print("Audio-face model already verified")
else:
    temporary = target.with_suffix(".partial")
    urllib.request.urlretrieve(entry["url"], temporary)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError("Audio-face model integrity check failed")
    temporary.replace(target)
    print("Audio-face model downloaded and verified")
