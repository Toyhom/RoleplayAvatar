"""Recover project SSH forwards when the remote service is healthy.

The watched names are written by demo.py. Model jobs are managed by GPUQ.
"""
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from roleplay_avatar.service_health import probe

STATE = ROOT / "outputs/services"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ALIASES = {"system-2": "system2", "system-3": "system3"}
failures = {}


def healthy(port):
    return probe(port, opener=OPENER).get("status") == "ready"


def recover(name, record):
    port = int(record["port"])
    alias = ALIASES[record["node"]]
    if not 1 <= port <= 65535:
        return
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); "
        "from roleplay_avatar.service_health import probe; "
        f"assert probe({port}).get('status')=='ready'"
    )
    options = record.get("ssh_options", ["-C", "-o", "IPQoS=none"])
    probe = subprocess.run(["ssh", *options, "-o", "ConnectTimeout=5", alias, "python3", "-c", shlex.quote(code)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
    if probe.returncode:
        return
    forward = f"127.0.0.1:{port}:127.0.0.1:{port}"
    pid = record["pid"]
    cmdline = Path(f"/proc/{pid}/cmdline")
    if cmdline.exists():
        arguments = cmdline.read_bytes().split(b"\0")
        if forward.encode() not in arguments or b"ssh" != Path(os.fsdecode(arguments[0])).name.encode():
            return
        if os.getpgid(pid) != pid:
            return
        os.killpg(pid, signal.SIGTERM)
        for _ in range(20):
            if not cmdline.exists():
                break
            time.sleep(0.1)
    with (STATE / f"tunnel-{name}.log").open("a") as log:
        process = subprocess.Popen(["ssh", "-N", *options, "-o", "ExitOnForwardFailure=yes",
                                    "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
                                    "-L", forward, alias], stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    temporary = STATE / f"tunnel-{name}.json.tmp"
    temporary.write_text(json.dumps({"pid": process.pid, "port": port, "node": record["node"],
                                      "ssh_options": options}))
    temporary.replace(STATE / f"tunnel-{name}.json")
    print("FORWARD_RECOVERED", name, port, flush=True)


while True:
    try:
        names = json.loads((STATE / "watched-tunnels.json").read_text())
        for name in names:
            if not name.replace("_", "").isalnum():
                continue
            record = json.loads((STATE / f"tunnel-{name}.json").read_text())
            if record["node"] not in ALIASES:
                continue
            failures[name] = 0 if healthy(record["port"]) else failures.get(name, 0) + 1
            if failures[name] >= 2:
                recover(name, record)
                failures[name] = 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        pass  # A launcher may be replacing a record, or a node may be reconnecting.
    time.sleep(10)
