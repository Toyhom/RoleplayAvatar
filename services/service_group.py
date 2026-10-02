"""Supervise multiple model services inside one GPU allocation.

Children inherit CUDA_VISIBLE_DEVICES unchanged. A failed child stops the group
so the queue reports a concrete failure and the services can be restarted together.
"""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from roleplay_avatar.models import model_path

parser = argparse.ArgumentParser()
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--config-sha256", help="Expected configuration bytes when submitted through a queue")
args = parser.parse_args()
config_bytes = args.config.read_bytes()
if args.config_sha256 and hashlib.sha256(config_bytes).hexdigest() != args.config_sha256:
    raise ValueError("Service configuration changed after submission; submit the updated configuration")
configuration = json.loads(config_bytes)
folder = ROOT / "outputs/services" / ("group-" + os.environ.get("GPUQ_JOB_ID", str(os.getpid())))
folder.mkdir(parents=True, exist_ok=True)
processes = []
handles = []
env = dict(os.environ)
env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
env.setdefault("MODELSCOPE_CACHE", str(ROOT / ".cache/modelscope"))
env.setdefault("HF_HOME", str(ROOT / ".cache/huggingface"))


def shutdown(signum, frame):
    raise SystemExit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)
try:
    for name, service in configuration["services"].items():
        if not name.replace("_", "").isalnum():
            raise ValueError("Service names use letters, digits and underscores")
        model = service.get("model") or str(model_path(service["model_role"], check=True))
        command = [os.path.expandvars(service["python"]), str(ROOT / service["script"]),
                   "--model", os.path.expandvars(model), "--port", str(service["port"]), *service.get("args", [])]
        handle = (folder / (name + ".log")).open("a")
        handles.append(handle)
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
        processes.append((name, process))
        print("SERVICE_STARTED", name, process.pid, flush=True)
    while True:
        for name, process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited with code {process.returncode}; see {folder / (name + '.log')}")
        time.sleep(1)
finally:
    for _, process in processes:
        if process.poll() is None:
            process.terminate()
    for _, process in processes:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    for handle in handles:
        handle.close()
