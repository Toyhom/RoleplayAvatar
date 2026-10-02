"""Sentence-buffered adapters for Qwen3-TTS Base/CustomVoice and CosyVoice families.

The low-latency CosyVoice3 service is speech_service.py. This adapter converts a
complete sentence to 24 kHz PCM before emitting contiguous chunks.
"""

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MODELSCOPE_CACHE", str(ROOT / ".cache/modelscope"))
sys.path[:0] = [
    str(ROOT / "src"),
    str(ROOT / "third_party/cosyvoice"),
    str(ROOT / "third_party/cosyvoice/third_party/Matcha-TTS"),
]
sys.modules["flash_attn"] = None
sys.modules["xformers"] = None
from math import gcd

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from scipy.signal import resample_poly

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--backend", choices=["cosyvoice-auto", "qwen-base", "qwen-custom"], required=True)
parser.add_argument("--speaker", default="Vivian")
parser.add_argument("--language", default="Auto")
parser.add_argument("--port", type=int, default=18120)
args = parser.parse_args()
if args.backend == "cosyvoice-auto":
    from cosyvoice.cli.cosyvoice import AutoModel

    model = AutoModel(model_dir=args.model)
else:
    from qwen_tts import Qwen3TTSModel

    model = Qwen3TTSModel.from_pretrained(
        args.model, device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa"
    )
lock = asyncio.Lock()
app = FastAPI(title="Roleplay speech family adapter")


class Speech(BaseModel):
    character_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    text: str = Field(min_length=1, max_length=500)
    style: str = "neutral"
    intensity: float = Field(default=0.4, ge=0, le=1)
    delivery: dict = Field(default_factory=dict)


def reference(cid):
    folder = ROOT / "characters" / cid
    profile = json.loads((folder / "voice_profile.json").read_text())
    paths = [(folder / profile[k]).resolve() for k in ["reference_audio", "reference_text"]]
    if any(not p.is_relative_to(folder.resolve()) for p in paths):
        raise ValueError("Invalid voice path")
    if hashlib.sha256(paths[0].read_bytes()).hexdigest() != profile["reference_sha256"]:
        raise ValueError("Voice reference integrity check failed")
    return str(paths[0]), paths[1].read_text()


def synthesize(payload):
    if args.backend == "qwen-custom":
        waves, sr = model.generate_custom_voice(
            text=payload.text, language=args.language, speaker=args.speaker
        )
        wave = waves[0]
    else:
        audio, transcript = reference(payload.character_id)
        if args.backend == "qwen-base":
            waves, sr = model.generate_voice_clone(
                text=payload.text, language=args.language, ref_audio=audio, ref_text=transcript
            )
            wave = waves[0]
        else:
            if type(model).__name__ == "CosyVoice3":
                transcript = "You are a helpful assistant.<|endofprompt|>" + transcript
            chunks = list(
                model.inference_zero_shot(payload.text, transcript, audio, stream=False, text_frontend=False)
            )
            wave = np.concatenate([c["tts_speech"].detach().cpu().numpy().reshape(-1) for c in chunks])
            sr = model.sample_rate
    wave = np.asarray(wave, dtype=np.float32).reshape(-1)
    if sr != 24000:
        divisor = gcd(int(sr), 24000)
        wave = resample_poly(wave, 24000 // divisor, int(sr) // divisor)
    if not len(wave) or not np.isfinite(wave).all():
        raise ValueError("Invalid generated audio")
    return (np.clip(wave, -1, 1) * 32767).astype("<i2").tobytes()


@app.get("/healthz")
def health():
    return {
        "status": "ready",
        "backend": args.backend,
        "model_path": args.model,
        "streaming": "sentence-buffered",
        "sample_rate": 24000,
    }


@app.post("/speak")
async def speak(payload: Speech, request: Request):
    async def generate():
        async with lock:
            task = asyncio.create_task(asyncio.to_thread(synthesize, payload))
            try:
                pcm = await asyncio.shield(task)
                for offset in range(0, len(pcm), 19200):
                    if await request.is_disconnected():
                        return
                    piece = pcm[offset : offset + 19200]
                    yield (
                        json.dumps(
                            {
                                "pcm_base64": base64.b64encode(piece).decode(),
                                "sample_rate": 24000,
                                "sample_offset": offset // 2,
                                "sample_count": len(piece) // 2,
                            }
                        )
                        + "\n"
                    )
                yield json.dumps({"done": True, "total_samples": len(pcm) // 2}) + "\n"
            finally:
                # Keep the inference lease until a buffered native call has finished.
                await asyncio.shield(task)

    return StreamingResponse(generate(), media_type="application/x-ndjson")


uvicorn.run(app, host="127.0.0.1", port=args.port)
