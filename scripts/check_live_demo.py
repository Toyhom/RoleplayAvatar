"""Exercise the deployed model-backed websocket, including replacement and cancellation."""

import argparse
import asyncio
import base64
import json
import statistics
import time
import uuid
import wave
from pathlib import Path

import httpx
from websockets.asyncio.client import connect

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:18080")
parser.add_argument("--characters", nargs="+", help="Character IDs; default: current library")
parser.add_argument("--rounds", type=int, default=3)
parser.add_argument("--output", type=Path, default=Path("outputs/live-validation"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)


async def main():
    async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
        health = (await client.get(args.url + "/api/services")).json()
        library = (await client.get(args.url + "/api/characters")).json()
    capabilities = {c["profile"]["character_id"]: c["capabilities"] for c in library}
    characters = args.characters or list(capabilities)
    assert characters, "Create at least one character first"
    assert health["mode"] == "live" and health["llm"]["status"] == health["tts"]["status"] == "ready", health
    ws_url = args.url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    results = []
    health_samples = []
    async with connect(ws_url, proxy=None, max_size=2**22) as ws:
        for character in characters:
            for index in range(args.rounds):
                turn = uuid.uuid4().hex
                started = time.perf_counter()
                await ws.send(
                    json.dumps(
                        {
                            "type": "speak",
                            "turn_id": turn,
                            "character_id": character,
                            "text": "用一句简短的话向我问好。" if index == 0 else "请用一句简短的话鼓励我。",
                        }
                    )
                )
                pcm = bytearray()
                texts = []
                events = []
                first = None
                first_text = None
                sequence = 0
                async with asyncio.timeout(180):
                    while True:
                        event = json.loads(await ws.recv())
                        assert event.get("turn_id") == turn, event
                        assert event["sequence"] == sequence
                        sequence += 1
                        events.append(event)
                        assert event["type"] not in {"error", "request_error"}, event
                        if event["type"] == "text":
                            if first_text is None:
                                first_text = time.perf_counter() - started
                            texts.append(event["data"]["text"])
                        if event["type"] == "audio":
                            first = first if first is not None else time.perf_counter() - started
                            assert event["sample_offset"] == len(pcm) // 2
                            pcm.extend(base64.b64decode(event["data"]["pcm_base64"]))
                        if event["type"] == "turn_end":
                            assert event["data"]["total_samples"] == len(pcm) // 2
                            break
                assert len(pcm) > 2400 and texts
                if "face" not in capabilities[character]["active_streams"]:
                    assert not any(e["type"] == "face" for e in events)
                stem = args.output / f"{character}_{index:02d}"
                with wave.open(str(stem.with_suffix(".wav")), "wb") as handle:
                    handle.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                    handle.writeframes(pcm)
                stem.with_suffix(".jsonl").write_text(
                    "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events)
                )
                result = {
                    "character": character,
                    "round": index,
                    "first_text_s": first_text,
                    "first_audio_s": first,
                    "generation_s": time.perf_counter() - started,
                    "audio_s": len(pcm) / 48000,
                    "reply": "".join(texts),
                }
                results.append(result)
                print("TURN_PASS", json.dumps(result, ensure_ascii=False), flush=True)
                if index % 5 == 0 or index == args.rounds - 1:
                    async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                        sample = (await client.get(args.url + "/api/services")).json()
                    health_samples.append({"character": character, "round": index, "services": sample})
        old, new = uuid.uuid4().hex, uuid.uuid4().hex
        await ws.send(
            json.dumps(
                {
                    "type": "speak",
                    "turn_id": old,
                    "character_id": characters[0],
                    "text": "讲一段关于山谷的故事。",
                }
            )
        )
        async with asyncio.timeout(120):
            while json.loads(await ws.recv())["type"] != "audio":
                pass
            cancelled_at = time.perf_counter()
            await ws.send(json.dumps({"type": "cancel", "turn_id": old}))
            while json.loads(await ws.recv())["type"] != "cancelled":
                pass
        cancellation = time.perf_counter() - cancelled_at
        await ws.send(
            json.dumps(
                {"type": "speak", "turn_id": new, "character_id": characters[-1], "text": "请说你好。"}
            )
        )
        async with asyncio.timeout(120):
            while True:
                event = json.loads(await ws.recv())
                assert event.get("turn_id") == new, "old turn leaked after cancellation"
                assert event["type"] != "error", event
                if event["type"] == "turn_end":
                    break
    report = {
        "services": health,
        "rounds_per_character": args.rounds,
        "results": results,
        "health_samples": health_samples,
        "server_cancel_ack_s": cancellation,
        "old_turn_leak": False,
        "first_audio_median_s": statistics.median(r["first_audio_s"] for r in results),
        "latency_scope": "elapsed time from request to first WebSocket audio event",
    }
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("LIVE_DEMO_PASS", flush=True)


asyncio.run(main())
