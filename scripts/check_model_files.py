"""Verify downloaded model blobs against the official downloader's recorded SHA256 etags."""

import hashlib
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
model_root = Path(os.environ["AVATAR_MODEL_ROOT"])
results = []
for model in json.loads((root / "configs/models.lock.json").read_text())["models"]:
    target = model_root / model["repo_id"] / model["revision"]
    if not target.is_dir():
        continue
    for metadata in (target / ".cache/huggingface/download").rglob("*.metadata"):
        revision, etag, *_ = metadata.read_text().splitlines()
        if len(etag) != 64:
            continue
        relative = str(metadata.relative_to(target / ".cache/huggingface/download"))[:-9]
        path = target / relative
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(8 * 1024 * 1024):
                digest.update(chunk)
        assert digest.hexdigest() == etag, relative
        result = {
            "model": model["repo_id"],
            "revision": revision,
            "file": relative,
            "bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
        }
        results.append(result)
        print("MODEL_BLOB_PASS", model["repo_id"], relative, flush=True)
(root / "outputs/demo_setup").mkdir(parents=True, exist_ok=True)
(root / "outputs/demo_setup/model-integrity.json").write_text(json.dumps(results, indent=2) + "\n")
