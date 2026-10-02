import asyncio
import base64
import json

import httpx
import pytest

from roleplay_avatar.contracts import Segment
from roleplay_avatar.live import RemoteTTS


def use_stream(monkeypatch, messages):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="\n".join(json.dumps(m) for m in messages))
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))


def block(offset=0, rate=24000):
    return {
        "pcm_base64": base64.b64encode(b"\x01\x00" * 1500).decode(),
        "sample_rate": rate,
        "sample_offset": offset,
        "sample_count": 1500,
    }


async def consume(characters):
    segment = Segment(turn_id="test_live", segment_id=0, sequence=0, text="你好。")
    return [chunk async for chunk in RemoteTTS("http://tts").stream(segment, characters["dragon_demo"])]


def test_native_chunks_preserve_sample_clock(monkeypatch, characters):
    use_stream(monkeypatch, [block(), block(1500), {"done": True, "total_samples": 3000}])
    chunks = asyncio.run(consume(characters))
    assert [chunk.sample_offset for chunk in chunks[:4]] == [0, 960, 1500, 2460]
    assert all(not any(c.pcm_s16le) for c in chunks[4:])
    offset = 0
    for chunk in chunks:
        assert chunk.sample_offset == offset
        offset += len(chunk.pcm_s16le) // 2
    assert offset == 3000 + 260 * 24


@pytest.mark.parametrize(
    "messages",
    [
        [block(12)],
        [block(rate=22050)],
        [block(), {"done": True, "total_samples": 2}],
        [block()],
        [{"error": "NativeError"}],
    ],
)
def test_reject_broken_native_stream(monkeypatch, messages, characters):
    use_stream(monkeypatch, messages)
    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(consume(characters))


def test_symbol_only_fragment_never_calls_tts(monkeypatch, characters):
    def unexpected(**kwargs):
        raise AssertionError("symbol-only fragment must not reach the speech backend")

    monkeypatch.setattr(httpx, "AsyncClient", unexpected)

    async def check():
        segment = Segment(turn_id="symbol", segment_id=0, sequence=0, text="😊！")
        return [c async for c in RemoteTTS("http://tts").stream(segment, characters["dragon_demo"])]

    assert asyncio.run(check()) == []


def test_openai_model_receives_persona_and_streams_performance(monkeypatch, characters):
    from roleplay_avatar.live import RemoteLLM

    monkeypatch.setenv("AVATAR_LLM_BACKEND", "openai")
    monkeypatch.setenv("AVATAR_LLM_MODEL", "custom-roleplay")
    monkeypatch.setenv("AVATAR_LLM_API_KEY", "test-only-key")
    calls = []
    performance = json.dumps(
        {"text": "为你高兴！", "emotion": "happy", "intensity": 0.7, "action_intent": "acknowledge"},
        ensure_ascii=False,
    )

    def respond(request):
        calls.append(request)
        chunks = [performance[:17], performance[17:40], performance[40:]]
        body = (
            "".join(
                "data: " + json.dumps({"choices": [{"delta": {"content": chunk}}]}) + "\n\n"
                for chunk in chunks
            )
            + "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(respond), **kw)
    )
    llm = RemoteLLM("http://roleplay/v1")

    async def check():
        return [s async for s in llm.stream("openai-test", "我通过考试了！", characters["dragon_demo"])]

    segments = asyncio.run(check())
    assert len(segments) == 1 and segments[0].text == "为你高兴！"
    assert segments[0].emotion == "happy" and segments[0].action_intent == "acknowledge"
    request = calls[0]
    payload = json.loads(request.content)
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-only-key"
    assert payload["model"] == "custom-roleplay"
    assert characters["dragon_demo"].profile.persona in payload["messages"][0]["content"]
    assert json.loads(llm.histories["dragon_demo"][-1]["content"])["text"] == "为你高兴！"


def test_reply_format_repaired_once_and_preserved_across_turns(monkeypatch, characters):
    from roleplay_avatar.live import RemoteLLM

    monkeypatch.setenv("AVATAR_LLM_BACKEND", "local")
    calls = []
    direction = {"text": "我在这里。", "emotion": "soft", "intensity": 0.4, "action_intent": "speak"}

    def respond(request):
        calls.append(json.loads(request.content))
        text = "我在这里。" if len(calls) == 1 else json.dumps(direction, ensure_ascii=False)
        return httpx.Response(200, text=json.dumps({"text": text}) + "\n")

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(respond), **kw)
    )
    llm = RemoteLLM("http://roleplay")

    async def check():
        first = [s async for s in llm.stream("first", "你好", characters["dragon_demo"])]
        second = [s async for s in llm.stream("second", "继续", characters["dragon_demo"])]
        return first, second

    first, second = asyncio.run(check())
    assert len(first) == len(second) == 1
    assert len(calls) == 3
    assert "逐行JSON" in calls[1]["messages"][-1]["content"]
    assert json.loads(calls[2]["messages"][-2]["content"]) == direction


def test_reply_format_repair_stops_after_one_attempt(monkeypatch, characters):
    from roleplay_avatar.live import RemoteLLM

    monkeypatch.setenv("AVATAR_LLM_BACKEND", "local")
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, text=json.dumps({"text": "plain text"}) + "\n")

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(respond), **kw)
    )

    async def check():
        return [s async for s in RemoteLLM("http://roleplay").stream("bad", "hi", characters["dragon_demo"])]

    with pytest.raises(ValueError, match="valid performance"):
        asyncio.run(check())
    assert len(calls) == 2
