"""CosyVoice3 streaming service with fixed references and cancellation-aware token production."""

import argparse
import asyncio
import base64
import hashlib
import json
import os
import queue
import re
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MODELSCOPE_CACHE", str(ROOT / ".cache/modelscope"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "third_party/cosyvoice"))
sys.path.insert(0, str(ROOT / "third_party/cosyvoice/third_party/Matcha-TTS"))
# Use native attention for CosyVoice's Torch environment.
sys.modules["flash_attn"] = None
sys.modules["xformers"] = None

import numpy as np
import torch
import uvicorn
from cosyvoice.cli.cosyvoice import CosyVoice3
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from roleplay_avatar.contracts import Delivery
from roleplay_avatar.voice_direction import synthesis_direction

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--port", type=int, default=18120)
args = parser.parse_args()
torch.manual_seed(42)
# Match the upstream vocoder's inference example: deterministic convolution
# avoids selecting very large temporary workspaces for some short utterances.
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
model = CosyVoice3(args.model, fp16=False, load_trt=False, load_vllm=False)
assert model.sample_rate == 24000, "The internal contract requires 24 kHz; do not silently resample chunks."
characters = {}


def voice_reference(cid):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", cid):
        raise ValueError("Invalid character identifier")
    folder = ROOT / "characters" / cid
    profile = json.loads((folder / "voice_profile.json").read_text())
    reference = (folder / profile["reference_audio"]).resolve()
    transcript = (folder / profile["reference_text"]).resolve()
    if not reference.is_relative_to(folder.resolve()) or not transcript.is_relative_to(folder.resolve()):
        raise ValueError("Invalid voice asset path")
    expected = profile["reference_sha256"]
    if hashlib.sha256(reference.read_bytes()).hexdigest() != expected:
        raise ValueError("Voice reference failed integrity check")
    return str(reference), transcript.read_text(), cid + "_" + expected[:16]


production_lock = threading.Lock()
current_stop = None
current_errors = None
completed_requests = 0
cancelled_requests = 0
failed_requests = 0
original_inference = model.model.llm.inference


def cancellable_inference(*positional, **kwargs):
    stop = current_stop
    for token in original_inference(*positional, **kwargs):
        if stop is not None and stop.is_set():
            break
        yield token


model.model.llm.inference = cancellable_inference
original_llm_job = model.model.llm_job


def guarded_llm_job(*arguments):
    try:
        original_llm_job(*arguments)
    except Exception as exc:  # noqa: BLE001 -- report arbitrary third-party model errors
        if current_stop is None or not current_stop.is_set():
            traceback.print_exc()
            if current_errors is not None:
                current_errors.append(exc)
    finally:
        # Upstream sets this only on its happy path. Always release the native
        # streaming wait loop when token production terminates, including errors.
        model.model.llm_end_dict[arguments[-1]] = True


model.model.llm_job = guarded_llm_job
app = FastAPI(title="Roleplay CosyVoice3")


class Speech(BaseModel):
    character_id: str
    text: str = Field(min_length=1, max_length=300)
    style: str = "neutral"
    intensity: float = Field(default=0.4, ge=0, le=1)
    delivery: Delivery = Field(default_factory=Delivery)


@app.get("/healthz")
def health():
    return {
        "status": "ready",
        "backend": "cosyvoice3",
        "sample_rate": model.sample_rate,
        "characters": [
            p.name for p in (ROOT / "characters").iterdir() if (p / "voice_profile.json").is_file()
        ],
        "styles": ["neutral", "happy", "sad", "angry", "soft"],
        "device": torch.cuda.get_device_name(),
        "allocated_gib": round(torch.cuda.memory_allocated() / 2**30, 3),
        "peak_allocated_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
        "busy": production_lock.locked(),
        "native_requests": len(model.model.llm_end_dict),
        "completed_requests": completed_requests,
        "cancelled_requests": cancelled_requests,
        "failed_requests": failed_requests,
        "deterministic_cudnn": torch.backends.cudnn.deterministic,
    }


@app.post("/speak")
async def speak(payload: Speech, request: Request):
    try:
        reference, transcript, voice_key = await asyncio.to_thread(voice_reference, payload.character_id)
    except (ValueError, OSError, KeyError):
        raise HTTPException(404, "Voice reference unavailable") from None
    stop = threading.Event()
    events = queue.Queue(maxsize=8)

    def enqueue(value):
        while not stop.is_set():
            try:
                events.put(value, timeout=0.1)
                return
            except queue.Full:
                continue

    def produce():
        global current_stop, current_errors, completed_requests, cancelled_requests, failed_requests
        while not production_lock.acquire(timeout=0.1):
            if stop.is_set():
                return
        try:
            if stop.is_set():
                return
            current_stop = stop
            current_errors = []
            if voice_key not in characters:
                model.add_zero_shot_spk(
                    "You are a helpful assistant.<|endofprompt|>" + transcript, reference, voice_key
                )
                characters[voice_key] = reference
                while len(characters) > 16:
                    old = next(iter(characters))
                    characters.pop(old)
                    model.frontend.spk2info.pop(old, None)
            model.model.token_hop_len = 25  # native code grows this per request; reset first-chunk size
            started = time.perf_counter()
            offset = 0
            # Neutral uses the cached same-text prompt for voice stability.
            instruction = synthesis_direction(payload.style, payload.intensity, payload.delivery.model_dump())
            if instruction is None:
                iterator = model.inference_zero_shot(
                    payload.text,
                    "",
                    "",
                    zero_shot_spk_id=voice_key,
                    stream=True,
                    text_frontend=False,
                )
            else:
                iterator = model.inference_instruct2(
                    payload.text,
                    instruction,
                    reference,
                    stream=True,
                    text_frontend=False,
                )
            for result in iterator:
                if current_errors:
                    raise RuntimeError("Native speech token generation failed") from current_errors[0]
                if stop.is_set():
                    continue  # exhaust the cancelled backend so its per-request caches are released
                wave = result["tts_speech"].detach().float().cpu().numpy().reshape(-1)
                pcm = (np.clip(wave, -1, 1) * 32767).astype("<i2").tobytes()
                enqueue(
                    {
                        "pcm_base64": base64.b64encode(pcm).decode(),
                        "sample_offset": offset,
                        "sample_rate": model.sample_rate,
                        "sample_count": len(wave),
                        "available_s": time.perf_counter() - started,
                    }
                )
                offset += len(wave)
            if current_errors:
                raise RuntimeError("Native speech token generation failed") from current_errors[0]
            if stop.is_set():
                cancelled_requests += 1
            else:
                completed_requests += 1
            enqueue({"done": True, "total_samples": offset, "generation_s": time.perf_counter() - started})
        except Exception as exc:  # noqa: BLE001 -- report arbitrary third-party model errors
            # An early disconnect may leave fewer tokens than the native vocoder's
            # receptive field. It is an intentional cancellation, not failed speech.
            if stop.is_set():
                cancelled_requests += 1
            else:
                failed_requests += 1
                traceback.print_exc()
                enqueue({"error": type(exc).__name__})
        finally:
            stop.set()
            # There is only one native request while production_lock is held.
            # Native generator errors can bypass its normal dictionary cleanup.
            # Keep ownership until the native producer actually exits. Releasing
            # after a deadline would let two requests mutate the same caches.
            while any(not ended for ended in model.model.llm_end_dict.values()):
                time.sleep(0.05)
            if all(model.model.llm_end_dict.values()):
                model.model.tts_speech_token_dict.clear()
                model.model.llm_end_dict.clear()
                model.model.hift_cache_dict.clear()
            current_stop = None
            current_errors = None
            production_lock.release()
            try:
                events.put_nowait(None)
            except queue.Full:
                pass

    async def generate():
        thread = threading.Thread(target=produce, daemon=True)
        thread.start()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.to_thread(events.get, True, 0.2)
                except queue.Empty:
                    if not thread.is_alive():
                        break
                    continue
                if item is None:
                    break
                yield json.dumps(item) + "\n"
        finally:
            stop.set()
            # The cancelled producer owns the model lock until the native cache cleanup finishes.

    return StreamingResponse(generate(), media_type="application/x-ndjson")


metadata = {
    "node": os.environ.get("GPUQ_NODE"),
    "job": os.environ.get("GPUQ_JOB_REF"),
    "port": args.port,
    "status": "ready",
    "started": time.time(),
    "model": args.model,
}
(ROOT / f"outputs/services/tts-{args.port}.json").write_text(json.dumps(metadata, indent=2))
print("TTS_READY", json.dumps(metadata), flush=True)
uvicorn.run(app, host="127.0.0.1", port=args.port)
