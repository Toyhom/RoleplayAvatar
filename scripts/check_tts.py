"""Capture native streaming chunks and style samples from the running real TTS."""

import argparse
import base64
import json
import time
import wave
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:18120")
parser.add_argument("--output", type=Path, default=Path("outputs/tts-validation"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
text = "你好，欢迎来到这里。无论旅途多么漫长，我都会认真倾听你的故事，陪你一起寻找答案。"
reports = []
with httpx.Client(trust_env=False, timeout=180) as client:
    for character in ["humanoid_demo", "dragon_demo", "robot_demo"]:
        for style in ["neutral", "happy", "sad", "angry", "soft"]:
            started = time.perf_counter()
            chunks, pcm, done = [], bytearray(), None
            with client.stream(
                "POST", args.url + "/speak", json={"character_id": character, "text": text, "style": style}
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    event = json.loads(line)
                    assert "error" not in event, event
                    if event.get("done"):
                        done = event
                        continue
                    assert event["sample_offset"] == len(pcm) // 2
                    assert event["sample_rate"] == 24000
                    audio = base64.b64decode(event.pop("pcm_base64"))
                    assert len(audio) == event["sample_count"] * 2
                    pcm.extend(audio)
                    chunks.append({**event, "received_s": time.perf_counter() - started})
            elapsed = time.perf_counter() - started
            assert done and done["total_samples"] == len(pcm) // 2 and len(chunks) >= 2
            assert chunks[0]["received_s"] < elapsed
            stem = args.output / f"{character}_{style}"
            with wave.open(str(stem.with_suffix(".wav")), "wb") as output:
                output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                output.writeframes(pcm)
            report = {
                "character": character,
                "style": style,
                "text": text,
                "chunks": chunks,
                "first_chunk_s": chunks[0]["received_s"],
                "elapsed_s": elapsed,
                "audio_s": len(pcm) / 48000,
                "rtf": elapsed / (len(pcm) / 48000),
            }
            stem.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            reports.append(report)
            print("TTS_STREAM_PASS", character, style, round(report["rtf"], 3), flush=True)
(args.output / "report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2))
