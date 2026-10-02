"""Start/status/stop this project's GPUQ model services, SSH forwards and CPU web app.

Run start/stop from the authorized system1 administrator entrypoint. GPU jobs
and the web process run as the project owner. No global server configuration changes.
"""

import argparse
import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "outputs/services"
STATE.mkdir(parents=True, exist_ok=True)
config = {}
for line in (ROOT / ".local.env").read_text().splitlines():
    if line.strip() and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        config[key.split()[-1]] = os.path.expandvars(shlex.split(value)[0])
owner = config["AVATAR_OWNER"]
os.environ.update(config)
sys.path.insert(0, str(ROOT / "src"))
from roleplay_avatar.models import agent_config, configuration, model_path
from roleplay_avatar.service_health import probe

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["start", "status", "stop", "restart-web"])
parser.add_argument("--replace-changed", action="store_true", help="Replace this project's services whose launch configuration changed")
args = parser.parse_args()


def owner_command(command):
    return ["runuser", "-u", owner, "--", *command] if os.geteuid() == 0 else command


def gpuq(*argv):
    return subprocess.check_output(owner_command(["gpuq", *argv]), cwd=ROOT, text=True).strip()


def health(port, route="/healthz"):
    return probe(port, route, opener=opener)


def ssh_options(alias):
    """Optional project route, authenticated with the original server host key."""
    prefix = "AVATAR_SSH_" + alias.upper()
    host = config.get(prefix + "_HOST")
    options = ["-C", "-o", "IPQoS=none"]
    if host:
        key_alias = config.get(prefix + "_HOST_KEY_ALIAS")
        if not key_alias:
            raise ValueError(prefix + "_HOST_KEY_ALIAS must identify the trusted server key")
        port = int(config.get(prefix + "_PORT", "22"))
        options += ["-o", "HostName=" + host, "-o", f"Port={port}", "-o", "HostKeyAlias=" + key_alias]
    return options


def stop_process(record, marker):
    pid = record.get("pid")
    if not pid:
        return
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        if marker.encode() not in cmdline:
            raise RuntimeError("Process identity changed; refusing to signal it")
        if os.getpgid(pid) != pid:
            raise RuntimeError("Recorded process no longer owns its process group")
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except FileNotFoundError:
        return


jobs_path = STATE / "jobs.json"
jobs = json.loads(jobs_path.read_text()) if jobs_path.exists() else {}
if args.action == "status":
    print(
        json.dumps(
            {"web": health(18080), "services": health(18080, "/api/services"), "jobs": jobs},
            ensure_ascii=False,
            indent=2,
        )
    )
    sys.exit(0)
if os.geteuid() != 0:
    raise SystemExit(
        "Run start/stop through the authorized system1 administrator entrypoint; GPU jobs remain owner-scoped."
    )
if args.action == "stop":
    watcher = STATE / "tunnel-watcher.json"
    if watcher.exists():
        stop_process(json.loads(watcher.read_text()), "scripts/watch_tunnels.py")
    for service, ref in jobs.items():
        record = json.loads(gpuq("show", ref))
        if record["state"] in {"queued", "running", "stopping"}:
            print(gpuq("cancel", ref))
    path = STATE / "web-process.json"
    if path.exists():
        stop_process(json.loads(path.read_text()), "scripts/serve.sh")
    for path in STATE.glob("tunnel-*.json"):
        if path.name == "tunnel-watcher.json":
            continue
        stop_process(json.loads(path.read_text()), "ssh")
    print("Project services stopped.")
    sys.exit(0)

group_path = config.get("AVATAR_SERVICE_GROUP_CONFIG")
group_services = json.loads(Path(group_path).read_text())["services"] if group_path else {}
specs = {} if "tts" in group_services else {
    "tts": {
        "port": int(config.get("AVATAR_TTS_PORT", "18120")),
        "python": config["AVATAR_TTS_PYTHON"],
        "script": "services/speech_service.py",
        "model": str(model_path("tts", check=True)),
    },
}
accelerated = "roleplay" in configuration().get("inference", {})
if (agent_config("roleplay")["backend"] == "local" or accelerated) and config.get("AVATAR_LLM_IN_GROUP") != "1":
    specs["llm"] = {
        "port": int(config.get("AVATAR_LLM_PORT", "18110")),
        "python": config["AVATAR_LLM_PYTHON"],
        "script": "services/local_inference_service.py" if accelerated else config.get("AVATAR_LLM_SERVICE", "services/llm_service.py"),
        "gpus": int(config.get("AVATAR_LLM_GPUS", "1")),
        "model": str(model_path("roleplay", check=True)),
    }
    if accelerated:
        from roleplay_avatar.inference import engine_config, fingerprint

        spec = specs["llm"]
        spec["extra"] = ["--config-sha256", fingerprint(
            config=engine_config(overrides={"port": spec["port"]}), model=spec["model"]
        )]
if config.get("AVATAR_CONTROLLER_PYTHON") and "controller" not in group_services:
    specs["controller"] = {
        "port": int(config.get("AVATAR_CONTROLLER_PORT", "18111")),
        "python": config["AVATAR_CONTROLLER_PYTHON"],
        "script": "services/llm_service.py",
        "model": str(model_path("controller", check=True)),
        "extra": ["--role", "controller"],
        "gpus": int(config.get("AVATAR_CONTROLLER_GPUS", "1")),
    }
if config.get("AVATAR_AUDIO_FACE_PYTHON") and "audio_face" not in group_services:
    specs["audio_face"] = {
        "port": 18130,
        "python": config["AVATAR_AUDIO_FACE_PYTHON"],
        "script": "services/audio_face_service.py",
        "model": str(model_path("audio_face", check=True)),
    }
if config.get("AVATAR_ASR_PYTHON") and "asr" not in group_services:
    specs["asr"] = {
        "port": int(config.get("AVATAR_ASR_PORT", "18140")),
        "python": config["AVATAR_ASR_PYTHON"],
        "script": config.get("AVATAR_ASR_SERVICE", "services/whisper_service.py"),
        "model": str(model_path("asr", check=True)),
    }
if group_path:
    specs["control"] = {
        "python": str(Path(config["AVATAR_ENV_PREFIX"]) / "bin/python"),
        "script": "services/service_group.py", "config": group_path,
        "ports": {name: entry["port"] for name, entry in group_services.items()},
        "gpus": int(config.get("AVATAR_CONTROL_GPUS", "1")),
    }
for service, spec in (specs.items() if args.action == "start" else []):
    existing = json.loads(gpuq("show", jobs[service])) if service in jobs else None
    command = ["bash", str(ROOT / "scripts/gpu_worker.sh"), spec["python"], str(ROOT / spec["script"])]
    if "config" in spec:
        command += ["--config", spec["config"], "--config-sha256",
                    hashlib.sha256(Path(spec["config"]).read_bytes()).hexdigest()]
    else:
        command += ["--model", spec["model"], "--port", str(spec["port"]), *spec.get("extra", [])]
    changed = existing and (existing.get("command") != command or existing.get("gpus") != spec.get("gpus", 1))
    if changed and existing["state"] in {"queued", "running"}:
        if not args.replace_changed:
            raise SystemExit(f"{service} configuration changed. Use start --replace-changed to reload it.")
        gpuq("cancel", jobs[service])
        deadline = time.monotonic() + 40
        while existing["state"] in {"queued", "running", "stopping"}:
            if time.monotonic() >= deadline:
                raise SystemExit(f"{service} is still stopping. Re-run start after it exits.")
            time.sleep(1)
            existing = json.loads(gpuq("show", jobs[service]))
    if not existing or existing["state"] not in {"queued", "running"}:
        # A submission error is surfaced. Never retry an ambiguous submission automatically.
        ref = gpuq(
            "submit", "--node", "auto", "--name", f"avatar-live-{service}", "--gpus", str(spec.get("gpus", 1)), "--", *command
        )
        jobs[service] = ref
        jobs_path.write_text(json.dumps(jobs, indent=2))
    record = json.loads(gpuq("show", jobs[service]))
    print(service, jobs[service], record["state"], flush=True)
    if record["state"] == "queued":
        print("A model job is queued. Re-run start after GPUQ places it; do not bypass the queue.")
        continue
    node = record["node"]
    for routed_service, routed_port in spec.get("ports", {service: spec.get("port")}).items():
        path = STATE / f"tunnel-{routed_service}.json"
        old_tunnel = json.loads(path.read_text()) if path.exists() else {}
        alias = {"system-2": "system2", "system-3": "system3"}.get(node)
        route_changed = alias and (old_tunnel.get("node") != node or
                                    old_tunnel.get("port") != routed_port or
                                    old_tunnel.get("ssh_options") != ssh_options(alias))
        if node != "system-1" and (route_changed or health(routed_port)["status"] != "ready"):
            alias = {"system-2": "system2", "system-3": "system3"}[node]
            if path.exists():
                stop_process(json.loads(path.read_text()), "ssh")
                time.sleep(0.3)
            command = [
                "ssh",
                "-N",
                *ssh_options(alias),
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "ServerAliveInterval=30",
                "-o",
                "ServerAliveCountMax=3",
                "-L",
                f"127.0.0.1:{routed_port}:127.0.0.1:{routed_port}",
                alias,
            ]
            with (STATE / f"tunnel-{routed_service}.log").open("a") as log:
                process = subprocess.Popen(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            path.write_text(json.dumps({"pid": process.pid, "node": node, "port": routed_port,
                                        "ssh_options": ssh_options(alias)}))

watched = [name for service, spec in specs.items() for name in spec.get("ports", {service: spec.get("port")})]
(STATE / "watched-tunnels.json").write_text(json.dumps(watched))
watcher_path = STATE / "tunnel-watcher.json"
watcher = json.loads(watcher_path.read_text()) if watcher_path.exists() else {}
watcher_cmd = Path(f"/proc/{watcher.get('pid')}/cmdline")
if not watcher_cmd.exists() or b"scripts/watch_tunnels.py" not in watcher_cmd.read_bytes():
    with (STATE / "tunnel-watcher.log").open("a") as log:
        process = subprocess.Popen([sys.executable, str(ROOT / "scripts/watch_tunnels.py")],
                                   cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    watcher_path.write_text(json.dumps({"pid": process.pid}))

# Local agent URLs are made reachable on each configured creation-worker node.
# All reverse forwards terminate at the same project-owned local LLM endpoint.
agent_service = "control" if "control" in specs else ("controller" if "controller" in specs else "llm")
agent_port = group_services.get("controller", {}).get("port") if group_path else specs.get(agent_service, {}).get("port")
llm_node = json.loads(gpuq("show", jobs[agent_service]))["node"] if agent_service in specs and agent_service in jobs else None
for worker in filter(None, config.get("AVATAR_AGENT_WORKER_NODES", "").split(",") if llm_node else []):
    path = STATE / f"tunnel-agent-{worker}.json"
    if worker in {"system-1", llm_node}:
        # A service moved here; release its previous reverse-forward listener.
        if path.exists():
            stop_process(json.loads(path.read_text()), "ssh")
            path.unlink()
        continue
    alias = {"system-2": "system2", "system-3": "system3"}[worker]
    old = json.loads(path.read_text()) if path.exists() else {}
    if old.get("port") == agent_port and Path(f"/proc/{old.get('pid')}/cmdline").exists():
        continue
    if old:
        stop_process(old, "ssh")
    port = agent_port
    with (STATE / f"tunnel-agent-{worker}.log").open("a") as log:
        process = subprocess.Popen(
            [
                "ssh",
                "-N",
                *ssh_options(alias),
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "ServerAliveInterval=30",
                "-o",
                "ServerAliveCountMax=3",
                "-R",
                f"127.0.0.1:{port}:127.0.0.1:{port}",
                alias,
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    path.write_text(json.dumps({"pid": process.pid, "node": worker, "port": port}))

web_record = STATE / "web-process.json"
if web_record.exists() and (args.action == "restart-web" or health(18080).get("mode") != "live"):
    stop_process(json.loads(web_record.read_text()), "scripts/serve.sh")
    time.sleep(1)
if health(18080)["status"] != "ok":
    with (STATE / "web.log").open("a") as log:
        process = subprocess.Popen(
            owner_command(["env", "AVATAR_MODE=live", "bash", "scripts/serve.sh"]),
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    web_record.write_text(json.dumps({"pid": process.pid, "mode": "live", "port": 18080}))
deadline = time.monotonic() + 15
while health(18080)["status"] != "ok":
    if time.monotonic() >= deadline:
        raise SystemExit("Web startup failed; inspect outputs/services/web.log")
    time.sleep(0.2)
print(
    "Web entry: http://127.0.0.1:18080 ; models may still be loading. Run this script with status to inspect readiness."
)
