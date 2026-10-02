"""Fuse learned audio articulation and independent semantic expression direction."""

import base64
from dataclasses import replace

import httpx


def combine_face(speech, emotion, intensity):
    """Speech owns articulation; the director supplies a bounded expression layer."""

    def value(name):
        return max(0.0, min(1.0, float(speech.get(name, 0))))

    jaw = max(0, value("JawOpen") - value("MouthClose") * 0.35)
    # The generic assets need a larger visible opening than the source MMD rigs.
    jaw = min(1, jaw * 1.8)
    smile = (value("MouthSmileLeft") + value("MouthSmileRight")) / 2
    frown = (value("MouthFrownLeft") + value("MouthFrownRight")) / 2
    values = {
        "jaw_open": jaw,
        "mouth_round": max(value("MouthPucker"), value("MouthFunnel")),
        "mouth_wide": max(value("MouthStretchLeft"), value("MouthStretchRight")),
        "brow_up": value("BrowInnerUp"),
        "eye_squint": (value("EyeSquintLeft") + value("EyeSquintRight")) / 2,
        "happy": smile * 0.4,
        "sad": frown * 0.35,
        "angry": max(value("BrowDownLeft"), value("BrowDownRight")) * 0.4,
        "soft": 0.0,
    }
    if emotion in {"happy", "sad", "angry", "soft"}:
        values[emotion] = max(values[emotion], max(0, min(1, intensity)))
    return values


class RemoteAudioFace:
    """Predict with context and 160ms lookahead while preserving source PCM chunks."""

    def __init__(self, url):
        self.url = url.rstrip("/")

    async def annotate(self, chunks):
        history = b""
        pending = []
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(30, connect=5)) as client:

            async def flush(count):
                nonlocal history
                combined = history + b"".join(c.pcm_s16le for c in pending)
                response = await client.post(
                    self.url + "/predict",
                    json={
                        "pcm_base64": base64.b64encode(combined).decode(),
                        "sample_rate": 24000,
                    },
                )
                response.raise_for_status()
                result = response.json()
                if result["fps"] != 25 or not result["frames"]:
                    raise ValueError("Audio-face response has an invalid clock")
                cursor = len(history) // 2
                emitted = []
                for chunk in pending[:count]:
                    index = min(len(result["frames"]) - 1, cursor // 960)
                    coefficients = dict(zip(result["names"], result["frames"][index], strict=True))
                    emitted.append(replace(chunk, face_coefficients=coefficients))
                    cursor += chunk.sample_count
                history = (history + b"".join(c.pcm_s16le for c in pending[:count]))[-48000:]
                del pending[:count]
                return emitted

            async for chunk in chunks:
                pending.append(chunk)
                if len(pending) >= 16:
                    for ready in await flush(12):
                        yield ready
            if pending:
                for ready in await flush(len(pending)):
                    yield ready
