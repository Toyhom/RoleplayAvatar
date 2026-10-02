"""Local Whisper transcription for bounded microphone utterances; no audio is retained."""

import argparse
import asyncio
import base64
import binascii
import os
import sys
import time
from pathlib import Path

sys.modules["flash_attn"] = None
import numpy as np
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoProcessor, WhisperForConditionalGeneration

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--port", type=int, default=18140)
parser.add_argument("--language", default=os.environ.get("AVATAR_ASR_LANGUAGE", "auto"))
args = parser.parse_args()
assert torch.cuda.is_available(), "Start ASR within its GPUQ allocation"
processor = AutoProcessor.from_pretrained(args.model, local_files_only=True)
model = (
    WhisperForConditionalGeneration.from_pretrained(
        args.model, torch_dtype=torch.float16, local_files_only=True, attn_implementation="sdpa"
    )
    .to("cuda")
    .eval()
)
lock = asyncio.Lock()
app = FastAPI(title="Roleplay microphone transcription")
completed = 0


class Audio(BaseModel):
    pcm_base64: str = Field(min_length=2, max_length=1_280_000)
    sample_rate: int = Field(default=16000, ge=16000, le=16000)


def transcribe(samples):
    batch = processor(samples, sampling_rate=16000, return_tensors="pt", return_attention_mask=True)
    with torch.inference_mode():
        output = model.generate(
            input_features=batch.input_features.to("cuda", dtype=torch.float16),
            attention_mask=batch.attention_mask.to("cuda"),
            language=args.language if args.language != "auto" and model.config.vocab_size >= 51865 else None,
            task="transcribe",
            max_new_tokens=256,
            do_sample=False,
        )
    return processor.batch_decode(output, skip_special_tokens=True)[0].strip()


@app.get("/healthz")
def health():
    return {
        "status": "ready",
        "backend": str(Path(args.model).name),
        "model_path": args.model,
        "sample_rate": 16000,
        "max_duration_s": 30,
        "completed_requests": completed,
    }


@app.post("/transcribe")
async def recognize(payload: Audio):
    global completed
    try:
        raw = base64.b64decode(payload.pcm_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, "Invalid PCM encoding") from None
    if len(raw) % 2 or not 6400 <= len(raw) <= 960000:
        raise HTTPException(422, "Expected 0.2 to 30 seconds of mono PCM16 at 16kHz")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    rms = float(np.sqrt(np.mean(samples**2)))
    if rms < 0.004:
        return {"text": "", "reason": "silence", "duration_s": len(samples) / 16000}
    started = time.monotonic()
    async with lock:
        text = await asyncio.to_thread(transcribe, samples)
        completed += 1
    return {
        "text": text,
        "duration_s": len(samples) / 16000,
        "inference_s": time.monotonic() - started,
        "backend": str(Path(args.model).name),
        "model_path": args.model,
    }


uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
