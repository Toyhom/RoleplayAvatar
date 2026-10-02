import asyncio
import base64
import json

import httpx
import pytest

from roleplay_avatar.adapters import AudioChunk
from roleplay_avatar.performance import RemoteAudioFace, combine_face


def test_director_does_not_replace_audio_articulation():
    speech = {"JawOpen": 0.4, "MouthClose": 0.1, "MouthPucker": 0.7, "MouthSmileLeft": 0.2}
    neutral = combine_face(speech, "neutral", 0.7)
    happy = combine_face(speech, "happy", 0.8)
    assert neutral["jaw_open"] == happy["jaw_open"] == pytest.approx(0.657)
    assert happy["happy"] == 0.8 and happy["mouth_round"] == 0.7
    assert all(0 <= v <= 1 for v in combine_face({"JawOpen": 9, "MouthPucker": -3}, "angry", 5).values())


def test_audio_face_buffers_without_altering_or_losing_pcm(monkeypatch):
    calls = []

    def respond(request):
        body = json.loads(request.content)
        pcm = base64.b64decode(body["pcm_base64"])
        calls.append(pcm)
        n = (len(pcm) // 2 + 959) // 960
        return httpx.Response(
            200, json={"fps": 25, "names": ["JawOpen"], "frames": [[0.1 + i * 0.005] for i in range(n)]}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(respond), **kw)
    )
    inputs = [AudioChunk(bytes([i, 0]) * 960, i * 960) for i in range(29)]
    inputs.append(AudioChunk(b"\x01\x00" * 480, 29 * 960))

    async def source():
        for c in inputs:
            yield c

    async def check():
        return [c async for c in RemoteAudioFace("http://face").annotate(source())]

    outputs = asyncio.run(check())
    assert [c.sample_offset for c in outputs] == [c.sample_offset for c in inputs]
    assert b"".join(c.pcm_s16le for c in outputs) == b"".join(c.pcm_s16le for c in inputs)
    assert all(c.face_coefficients["JawOpen"] > 0 for c in outputs)
    assert len(calls) == 3
    assert len(calls[0]) == 16 * 1920  # 480ms output plus 160ms future context


def test_cancel_during_audio_face_request_closes_tts(characters, monkeypatch):
    from roleplay_avatar.contracts import CharacterPackage, SpeakRequest
    from roleplay_avatar.session import Session

    async def run():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        closed, events = [], []

        async def respond(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        original = httpx.AsyncClient
        monkeypatch.setattr(
            httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(respond), **kw)
        )

        class TTS:
            async def stream(self, segment, character):
                try:
                    for index in range(30):
                        yield AudioChunk(b"\0\0" * 960, index * 960)
                finally:
                    closed.append(segment.turn_id)

        data = characters["humanoid_demo"].model_dump()
        data["capabilities"].update(face_mode="blendshape", active_streams=["audio", "motion", "face"])
        data["face_map"]["channels"] = [
            {"source": "jaw_open", "target": "jaw_open", "minimum": 0, "maximum": 1}
        ]
        character = CharacterPackage.model_validate(data)

        async def send(event):
            events.append(event)

        session = Session(
            send, {"humanoid_demo": character}, TTS(), audio_face=RemoteAudioFace("http://face")
        )
        await session.start(
            SpeakRequest(type="speak", turn_id="buffered", character_id="humanoid_demo", text="你好")
        )
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(session.cancel("buffered"), 2)
        assert cancelled.is_set() and closed == ["buffered"]
        assert events[-1]["type"] == "cancelled"
        assert not any(e["type"] in {"audio", "face", "turn_end", "error"} for e in events)

    asyncio.run(run())


def test_2d_only_face_emits_audio_clock_performance(characters):
    from roleplay_avatar.adapters import ToneReplayTTS
    from roleplay_avatar.contracts import CharacterPackage, SpeakRequest
    from roleplay_avatar.session import Session

    data = characters["humanoid_demo"].model_dump()
    assert not data["face_map"]["channels"]
    data["profile"].update(presentation_modes=["2d"], model=None)
    data["face_map"]["channels"] = [
        {"source": n, "target": n, "renderers": ["2d"]} for n in ["jaw_open", "happy"]
    ]
    data["capabilities"].update(face_mode="blendshape", active_streams=["audio", "motion", "face"])
    package = CharacterPackage.model_validate(data)
    assert package.capabilities.active_streams == ["audio", "motion", "face"]
    assert all(c.renderers == ["2d"] for c in package.face_map.channels)

    async def run():
        events = []

        async def send(event):
            events.append(event)

        session = Session(send, {"humanoid_demo": package}, ToneReplayTTS(duration_samples=960, paced=False))
        await session.start(
            SpeakRequest(type="speak", turn_id="portrait", character_id="humanoid_demo", text="你好")
        )
        await session.task
        facial = [e for e in events if e["type"] == "face"]
        assert facial and any(e["data"]["values"]["jaw_open"] > 0 for e in facial)
        assert events[-1]["type"] == "turn_end"

    asyncio.run(run())
