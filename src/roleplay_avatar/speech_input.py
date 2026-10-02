"""Bounded microphone PCM proxy; transcription stays separate from conversation turns."""

import base64
import binascii
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class MicrophoneAudio(BaseModel):
    pcm_base64: str = Field(min_length=2, max_length=1_280_000)
    sample_rate: int = Field(default=16000, ge=16000, le=16000)


def speech_routes():
    router = APIRouter(prefix="/api")

    @router.post("/transcribe")
    async def transcribe(payload: MicrophoneAudio):
        url = os.environ.get("AVATAR_ASR_URL")
        if not url:
            raise HTTPException(503, "语音识别服务尚未配置")
        try:
            pcm = base64.b64decode(payload.pcm_base64, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(422, "录音格式无效") from None
        if len(pcm) % 2 or not 6400 <= len(pcm) <= 960000:
            raise HTTPException(422, "请录制 0.2 至 30 秒的语音")
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=60) as client:
                response = await client.post(url.rstrip("/") + "/transcribe", json=payload.model_dump())
                response.raise_for_status()
                result = response.json()
            if not isinstance(result, dict):
                raise TypeError("Invalid transcription response")
            text = result.get("text")
            if not isinstance(text, str) or len(text) > 1000:
                raise ValueError("Invalid transcription")
        except (httpx.HTTPError, ValueError, TypeError):
            raise HTTPException(502, "语音识别暂时失败，请重试") from None
        return {"text": text, "duration_s": len(pcm) / 32000, "reason": result.get("reason")}

    return router
