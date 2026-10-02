"""Verify the documented serve launcher over real HTTP and WebSocket sockets, then stop it."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from websockets.asyncio.client import connect

root = Path(__file__).resolve().parents[1]
output = root / "outputs/initialization"
output.mkdir(parents=True, exist_ok=True)


async def check(port):
    async with connect(f"ws://127.0.0.1:{port}/ws", proxy=None) as ws:
        await ws.send(
            json.dumps({"type": "speak", "turn_id": "live_1", "character_id": "robot_demo", "text": "你好"})
        )
        events = []
        async with asyncio.timeout(10):
            while True:
                event = json.loads(await ws.recv())
                events.append(event)
                if event["type"] == "turn_end":
                    break
                if event["type"] in {"error", "request_error"}:
                    raise RuntimeError(event)
        assert events[-1]["data"]["total_samples"] == 72000
        assert not any(e["type"] == "face" for e in events)
        await ws.send(
            json.dumps(
                {"type": "speak", "turn_id": "live_2", "character_id": "dragon_demo", "text": "请停下"}
            )
        )
        async with asyncio.timeout(5):
            while json.loads(await ws.recv())["type"] != "audio":
                pass
            await ws.send(json.dumps({"type": "cancel", "turn_id": "live_2"}))
            while json.loads(await ws.recv())["type"] != "cancelled":
                pass
        return {
            "http": "passed",
            "websocket_complete": "passed",
            "websocket_cancel": "passed",
            "event_count": len(events),
            "total_samples": 72000,
            "audio_kind": "diagnostic_tone",
            "browser_audio_and_rendering": "not_tested",
        }


with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
env = {
    **os.environ,
    "AVATAR_MODE": "replay",
    "AVATAR_ENV_PREFIX": sys.prefix,
    "AVATAR_HOST": "127.0.0.1",
    "AVATAR_PORT": str(port),
}
command = ["bash", "scripts/serve.sh"]
with (output / "server.log").open("w") as log:
    process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 15
        with httpx.Client(trust_env=False) as client:
            while True:
                if process.poll() is not None:
                    raise RuntimeError("server exited; inspect outputs/initialization/server.log")
                try:
                    response = client.get(f"http://127.0.0.1:{port}/healthz", timeout=1)
                    response.raise_for_status()
                    break
                except httpx.TransportError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
            assert response.json()["mode"] == "diagnostic_tone"
            assert client.get(f"http://127.0.0.1:{port}/").status_code == 200
        report = asyncio.run(check(port))
        (output / "live-server.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
