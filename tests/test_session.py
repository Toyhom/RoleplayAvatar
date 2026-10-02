import asyncio
import base64

import pytest

from roleplay_avatar.adapters import AudioChunk, ToneReplayTTS
from roleplay_avatar.contracts import SpeakRequest
from roleplay_avatar.session import Session


def request(turn, character="robot_demo"):
    return SpeakRequest(type="speak", turn_id=turn, character_id=character, text="你好")


@pytest.mark.parametrize("character", ["humanoid_demo", "dragon_demo", "robot_demo"])
def test_30_turns_finish_without_face_and_keep_sample_clock(characters, character):
    async def run():
        events = []

        async def send(event):
            events.append(event)

        session = Session(send, characters, ToneReplayTTS(duration_samples=4800, paced=False))
        for index in range(30):
            events.clear()
            await session.start(request(f"turn_{index}", character))
            await asyncio.wait_for(session.task, timeout=2)
            assert events[-1]["type"] == "turn_end"
            assert [e["sequence"] for e in events] == list(range(len(events)))
            assert "face" not in [e["type"] for e in events]
            ended = {e["data"]["stream"] for e in events if e["type"] == "stream_end"}
            assert ended == {"audio", "motion"}
            offset = 0
            for event in (e for e in events if e["type"] == "audio"):
                assert event["sample_offset"] == offset
                assert len(base64.b64decode(event["data"]["pcm_base64"])) == event["data"]["sample_count"] * 2
                offset += event["data"]["sample_count"]
            assert offset == events[-1]["data"]["total_samples"] == 14400
        await session.cancel(notify=False)

    asyncio.run(run())


def test_replace_and_cancel_close_producer_and_drop_old_turn(characters):
    async def run():
        events, closed = [], []
        arrived = asyncio.Queue()

        class BlockingTTS:
            async def stream(self, segment, character):
                try:
                    yield AudioChunk(b"\0\0" * 24, 0)
                    await asyncio.Event().wait()
                finally:
                    closed.append(segment.turn_id)

        async def send(event):
            events.append(event)
            if event["type"] == "audio":
                arrived.put_nowait(event)

        session = Session(send, characters, BlockingTTS())
        await session.start(request("old"))
        await asyncio.wait_for(arrived.get(), 1)
        await session.start(request("new"))
        await asyncio.wait_for(arrived.get(), 1)
        await session.cancel("old")
        assert not session.task.done()
        await session.cancel("new")
        assert closed == ["old", "new"]
        old_cancel = next(
            i for i, e in enumerate(events) if e["type"] == "cancelled" and e["turn_id"] == "old"
        )
        assert all(e["turn_id"] == "new" for e in events[old_cancel + 1 :])
        assert events[-1]["type"] == "cancelled"
        with pytest.raises(ValueError, match="unique"):
            await session.start(request("new"))

    asyncio.run(run())


def test_bad_audio_offset_fails_visibly(characters):
    async def run():
        events = []

        class BrokenTTS:
            async def stream(self, segment, character):
                yield AudioChunk(b"\0\0", 2400)

        async def send(event):
            events.append(event)

        session = Session(send, characters, BrokenTTS())
        await session.start(request("bad"))
        await session.task
        assert events[-1]["type"] == "error"
        assert all(e["type"] != "turn_end" for e in events)

    asyncio.run(run())
