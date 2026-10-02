"""CTranslate2 microphone recognition with FP16 or INT8 weights."""

import argparse
import asyncio
import base64
import binascii
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class Audio(BaseModel):
    pcm_base64: str = Field(min_length=2, max_length=1_280_000)
    sample_rate: int = Field(default=16000, ge=16000, le=16000)


def create_app(model, *, model_path, compute_type="int8_float16", language="auto", beam_size=1):
    import numpy as np

    app = FastAPI(title="Roleplay CTranslate2 microphone transcription")
    lock = asyncio.Lock()
    completed = 0

    def transcribe(samples):
        segments, info = model.transcribe(samples, language=None if language == "auto" else language,
                                         beam_size=beam_size, condition_on_previous_text=False,
                                         vad_filter=False, temperature=0)
        return "".join(segment.text for segment in segments).strip(), info.language

    @app.get("/healthz")
    def health():
        return {"status": "ready", "backend": "faster-whisper", "model_path": str(model_path),
                "compute_type": compute_type, "sample_rate": 16000, "max_duration_s": 30,
                "completed_requests": completed}

    @app.post("/transcribe")
    async def recognize(payload: Audio):
        nonlocal completed
        try:
            raw = base64.b64decode(payload.pcm_base64, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(422, "Invalid PCM encoding") from None
        if len(raw) % 2 or not 6400 <= len(raw) <= 960000:
            raise HTTPException(422, "Expected 0.2 to 30 seconds of mono PCM16 at 16kHz")
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
        if float(np.sqrt(np.mean(samples**2))) < 0.004:
            return {"text": "", "reason": "silence", "duration_s": len(samples) / 16000}
        started = time.monotonic()
        async with lock:
            task = asyncio.create_task(asyncio.to_thread(transcribe, samples))
            try:
                text, detected = await asyncio.shield(task)
                completed += 1
            finally:
                # Native inference retains the model lease until it actually finishes.
                await asyncio.shield(task)
        return {"text": text, "language": detected, "duration_s": len(samples) / 16000,
                "inference_s": time.monotonic() - started, "backend": "faster-whisper"}

    return app


def main():
    import uvicorn
    from faster_whisper import WhisperModel

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Local CTranslate2 checkpoint directory")
    parser.add_argument("--port", type=int, default=18140)
    parser.add_argument("--device", choices=["cuda", "cpu", "auto"], default="cuda")
    parser.add_argument("--compute-type", choices=["float16", "float32", "int8_float16", "int8"], default="int8_float16")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--beam-size", type=int, choices=range(1, 11), default=1)
    parser.add_argument("--warmup", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    path = Path(args.model).expanduser().resolve()
    if not (path / "model.bin").is_file():
        raise ValueError("Expected a CTranslate2 model.bin; convert your Whisper checkpoint first")
    model = WhisperModel(str(path), device=args.device, compute_type=args.compute_type, local_files_only=True)
    if args.warmup:
        import numpy as np

        segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language="en", beam_size=1,
                                       condition_on_previous_text=False, vad_filter=False)
        list(segments)
    app = create_app(model, model_path=path, compute_type=args.compute_type,
                     language=args.language, beam_size=args.beam_size)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
