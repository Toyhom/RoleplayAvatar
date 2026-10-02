import base64

import httpx
from conftest import ROOT
from fastapi.testclient import TestClient

from roleplay_avatar.app import create_app


def test_microphone_validation_and_recognition_proxy(monkeypatch):
    monkeypatch.setenv("AVATAR_ASR_URL", "http://asr")
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"text": "你好，带我看看森林。"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(respond), **kw)
    )
    with TestClient(create_app(ROOT, mode="replay")) as client:
        for pcm in [
            "invalid!",
            base64.b64encode(b"a" * 6401).decode(),
            base64.b64encode(b"a" * 100).decode(),
        ]:
            assert client.post("/api/transcribe", json={"pcm_base64": pcm}).status_code == 422
        assert not calls
        payload = {"pcm_base64": base64.b64encode(b"\0\0" * 16000).decode(), "sample_rate": 16000}
        assert (
            client.post(
                "/api/transcribe", json=payload, headers={"Origin": "https://elsewhere.example"}
            ).status_code
            == 403
        )
        result = client.post("/api/transcribe", json=payload)
        assert result.json()["text"] == "你好，带我看看森林。" and result.json()["duration_s"] == 1
        assert len(calls) == 1 and calls[0].url.path == "/transcribe"
        assert client.post("/api/transcribe", json={**payload, "sample_rate": 48000}).status_code == 422


def test_microphone_unconfigured_or_failed_service_is_explicit(monkeypatch):
    monkeypatch.delenv("AVATAR_ASR_URL", raising=False)
    payload = {"pcm_base64": base64.b64encode(b"\0\0" * 16000).decode()}
    with TestClient(create_app(ROOT, mode="replay")) as client:
        assert client.post("/api/transcribe", json=payload).status_code == 503
    monkeypatch.setenv("AVATAR_ASR_URL", "http://asr")
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(lambda _: httpx.Response(500)), **kw),
    )
    with TestClient(create_app(ROOT, mode="replay")) as client:
        assert client.post("/api/transcribe", json=payload).status_code == 502
