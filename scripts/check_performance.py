"""Verify automatic reply direction and real speech after changing a generated voice."""

import argparse
import asyncio
import base64
import hashlib
import json
import time
import uuid
import wave
from pathlib import Path

import httpx
from websockets.asyncio.client import connect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:18080")
parser.add_argument("--character", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)


async def turn(label, prompt, expected):
    started = time.monotonic()
    pcm, directions, events = bytearray(), [], []
    first = None
    turn_id = uuid.uuid4().hex
    url = args.url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    # Separate conversation contexts ensure the emotional probes do not prime each other.
    async with connect(url, proxy=None, max_size=2**22) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "speak",
                    "turn_id": turn_id,
                    "character_id": args.character,
                    "text": prompt,
                    "emotion": "auto",
                }
            )
        )
        async with asyncio.timeout(180):
            while True:
                event = json.loads(await ws.recv())
                assert event.get("turn_id") == turn_id, event
                assert event["type"] not in {"error", "request_error"}, event
                events.append(event)
                if event["type"] == "text":
                    directions.append(event["data"])
                if event["type"] == "audio":
                    assert event["sample_offset"] == len(pcm) // 2
                    pcm.extend(base64.b64decode(event["data"]["pcm_base64"]))
                    if first is None:
                        first = time.monotonic() - started
                if event["type"] == "turn_end":
                    assert event["data"]["total_samples"] == len(pcm) // 2
                    break
    assert len(pcm) > 2400 and directions
    assert any(d["emotion"] in expected for d in directions), directions
    assert all(d["style"] == d["emotion"] for d in directions), directions
    facial = [e for e in events if e["type"] == "face"]
    if facial:
        assert any(max(e["data"]["values"].values()) > 0 for e in facial)
        for direction in directions:
            if direction["emotion"] == "neutral":
                continue
            relevant = [e for e in facial if e["segment_id"] == direction["segment_id"]]
            assert relevant
            assert any(e["data"]["values"].get(direction["emotion"], 0) > 0 for e in relevant)
    with wave.open(str(args.output / f"{label}.wav"), "wb") as out:
        out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        out.writeframes(pcm)
    (args.output / f"{label}.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events)
    )
    result = {
        "probe": label,
        "prompt": prompt,
        "directions": directions,
        "first_audio_s": first,
        "audio_s": len(pcm) / 48000,
        "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "facial_events": len(facial),
    }
    print("PERFORMANCE_PASS", json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def main():
    results = []
    results.append(
        await turn("joy", "我终于完成了冒险，还救下了所有伙伴！请开心地为我庆祝，一句话就好。", {"happy"})
    )
    results.append(
        await turn("comfort", "我最珍惜的朋友离开了，我很难过。请温柔地安慰我，一句话就好。", {"soft", "sad"})
    )
    async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
        path = args.url + f"/api/characters/{args.character}"
        voices = (await client.get(path + "/studio")).json()["voices"]
        original = voices["selected"]
        alternative = original % 3 + 1
        try:
            response = await client.post(path + "/voice", json={"candidate": alternative})
            response.raise_for_status()
            current = (await client.get(path)).json()["voice_profile"]
            selected = next(v for v in voices["candidates"] if v["candidate"] == alternative)
            assert current["reference_sha256"] == selected["sha256"]
            sample = await client.get(args.url + f"/assets/{args.character}/reference.wav")
            assert hashlib.sha256(sample.content).hexdigest() == selected["sha256"]
            results.append(
                await turn("changed-voice", "请用一句话介绍你的名字与身份。", {"neutral", "soft", "happy"})
            )
        finally:
            restored = await client.post(path + "/voice", json={"candidate": original})
            restored.raise_for_status()
    (args.output / "report.json").write_text(
        json.dumps(
            {
                "character": args.character,
                "results": results,
                "voice_switch": {
                    "original": original,
                    "tested": alternative,
                    "reference_sha256": selected["sha256"],
                    "restored": True,
                },
                "scope": "Actual model directions, PCM and facial controls; not a perceptual voice similarity score.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


asyncio.run(main())
