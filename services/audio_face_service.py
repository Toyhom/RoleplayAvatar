"""DLP3D UniTalker ONNX inference; audio-only direction kept separate from the LLM."""

import argparse
import asyncio
import base64
import json
import os
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch  # Load the matching CUDA/cuDNN libraries before the ONNX CUDA provider.
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--port", type=int, default=18130)
args = parser.parse_args()
assert torch.cuda.is_available(), "Run the audio-face service in its GPUQ allocation"
session = ort.InferenceSession(args.model, providers=["CUDAExecutionProvider"])
assert session.get_providers()[0] == "CUDAExecutionProvider", "CUDA provider must actually load"
names = json.loads((ROOT / "configs/audio-face-names.json").read_text())
lock = asyncio.Lock()
app = FastAPI(title="Roleplay UniTalker audio expressions")
requests_completed = 0


class Audio(BaseModel):
    pcm_base64: str = Field(max_length=512000)
    sample_rate: int = Field(default=24000, ge=24000, le=24000)


def infer(pcm):
    raw = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if not 960 <= len(raw) <= 144000:
        raise ValueError("Expected 40ms to 6s of mono PCM16")
    frames = max(1, int(np.ceil(len(raw) / 960)))
    wave = resample_poly(raw, 2, 3).astype(np.float32)
    # Same zero-mean/unit-variance preprocessing as upstream Wav2Vec2FeatureExtractor.
    wave = (wave - wave.mean()) / np.sqrt(wave.var() + 1e-7)
    if len(wave) < 8512:
        wave = np.pad(wave, (0, 8512 - len(wave)))
    count = max(frames, int(len(wave) * 25 / 16000))
    output = session.run(None, {"audio": wave[None], "emo_id": np.array([10], np.int32),
                                "time_steps": np.array([count], np.int32)})[0][0]
    if output.shape != (count, len(names)) or not np.isfinite(output).all():
        raise ValueError("Invalid UniTalker output")
    output = np.clip(output[:frames], 0, 1)
    # Silence must settle the mouth, regardless of normalized background noise.
    for i in range(frames):
        segment = raw[i * 960:(i + 1) * 960]
        if len(segment) and np.sqrt(np.mean(segment**2)) < 0.004:
            output[i, 19:] *= 0
    return output.tolist()


@app.get("/healthz")
def health():
    return {"status": "ready", "backend": "dlp3d-unitalker-v0.4.0", "fps": 25,
            "channels": len(names), "provider": session.get_providers()[0],
            "completed_requests": requests_completed}


@app.post("/predict")
async def predict(payload: Audio):
    global requests_completed
    pcm = base64.b64decode(payload.pcm_base64, validate=True)
    async with lock:
        started = time.monotonic()
        output = await asyncio.to_thread(infer, pcm)
        requests_completed += 1
    return {"names": names, "frames": output, "fps": 25,
            "backend": "dlp3d-unitalker-v0.4.0", "inference_s": time.monotonic() - started}


(ROOT / "outputs/services/audio-face.json").write_text(json.dumps({
    "node": os.environ.get("GPUQ_NODE"), "job": os.environ.get("GPUQ_JOB_REF"),
    "port": args.port, "model": args.model, "status": "ready",
}))
uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
