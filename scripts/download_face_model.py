"""Download the versioned official CPU face landmark task with a locked SHA256."""

import hashlib
import json
import os
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
entry = json.loads((root / "configs/creation-models.lock.json").read_text())["face_landmarker"]
target = Path(os.environ["AVATAR_MODEL_ROOT"]) / entry["relative_path"]
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]:
    print("Face model already verified")
else:
    temporary = target.with_suffix(".partial")
    urllib.request.urlretrieve(entry["url"], temporary)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError("Face model integrity check failed")
    temporary.replace(target)
    print("Face model downloaded and verified")
