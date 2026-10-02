"""Owner-scoped GPUQ witnesses for both voice environments, with saved job references."""

import json
import os
import shlex
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = {}
for line in (ROOT / ".local.env").read_text().splitlines():
    if line.strip() and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        config[key.split()[-1]] = shlex.split(value)[0]
if os.geteuid() == 0:
    raise SystemExit("Run this checker as the project owner, as documented.")
reports = []
for key in ["AVATAR_QWEN_PYTHON", "AVATAR_TTS_PYTHON"]:
    ref = subprocess.check_output(
        [
            "gpuq",
            "submit",
            "--node",
            "auto",
            "--name",
            "avatar-env-witness",
            "--gpus",
            "1",
            "--",
            "bash",
            str(ROOT / "scripts/gpu_worker.sh"),
            config[key],
            str(ROOT / "scripts/check_cuda.py"),
        ],
        cwd=ROOT,
        text=True,
    ).strip()
    print("SUBMITTED", key, ref, flush=True)
    deadline = time.monotonic() + 600
    while True:
        state = json.loads(subprocess.check_output(["gpuq", "show", ref], text=True))["state"]
        if state not in {"queued", "running", "stopping"}:
            break
        if time.monotonic() > deadline:
            raise RuntimeError(f"{ref} is still {state}; inspect this job before submitting again")
        time.sleep(2)
    logs = subprocess.check_output(["gpuq", "logs", ref], text=True)
    assert state == "succeeded" and "WITNESS" in logs, (ref, state, logs)
    reports.append({"environment": key, "job": ref, "state": state, "witness": logs.strip()})
    print(logs.strip(), flush=True)
(ROOT / "outputs/demo_setup/environment-witnesses.json").write_text(json.dumps(reports, indent=2) + "\n")
print("VOICE_ENVIRONMENTS_PASS", flush=True)
