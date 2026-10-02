"""Director controls must survive streaming, and use sentence-local audio time."""

import asyncio
import json

import pytest
from pydantic import ValidationError

from roleplay_avatar.adapters import ToneReplayTTS
from roleplay_avatar.contracts import ActionCue, Segment, SpeakRequest
from roleplay_avatar.live import PerformanceParser
from roleplay_avatar.session import Session


def test_split_model_output_preserves_actions_and_filters_invalid_controls():
    data = {
        "text": "我同意。",
        "emotion": "happy",
        "actions": [
            {"name": "nod", "start_s": 0.2, "duration_s": 1.8, "strength": 0.7},
            {"name": "wave_hand"},
            {"name": "bow", "duration_s": float("nan")},
        ],
    }
    wire = json.dumps(data, ensure_ascii=False)
    parser = PerformanceParser()
    output = []
    for char in wire:
        output.extend(parser.feed(char))
    assert len(output) == 1
    assert output[0]["text"] == "我同意。"
    assert output[0]["actions"] == [data["actions"][0]]
    malformed = PerformanceParser().feed('{"text":"你好。","emotion":[],"action_intent":{},"actions":{}}')[0]
    assert malformed["emotion"] == "neutral" and malformed["action_intent"] == "speak"
    assert malformed["actions"] == []
    assert PerformanceParser().feed('{"text":"安静地陪你。","actions":[]}')[0]["actions"] == []


@pytest.mark.parametrize(
    "cue",
    [
        {"name": "wave_hand"},
        {"name": "nod", "duration_s": -1},
        {"name": "bow", "strength": 2},
        {"name": "tilt", "start_s": float("inf")},
    ],
)
def test_invalid_controls_rejected_at_contract(cue):
    with pytest.raises(ValidationError):
        ActionCue.model_validate(cue)


def test_action_clock_restarts_per_sentence_and_matches_text_cues(characters):
    class LLM:
        async def stream(self, turn_id, text, character):
            for i, name in enumerate(["nod", "bow"]):
                yield Segment(
                    turn_id=turn_id, segment_id=i, sequence=i, text="你好。", actions=[ActionCue(name=name)]
                )

    async def run():
        events = []

        async def send(event):
            events.append(event)

        session = Session(
            send, characters, ToneReplayTTS(chunk_samples=960, duration_samples=2880, paced=False), LLM()
        )
        await session.start(
            SpeakRequest(type="speak", turn_id="actions", character_id="robot_demo", text="你好")
        )
        await session.task
        return events

    events = asyncio.run(run())
    assert events[-1]["type"] == "turn_end"
    for i in range(2):
        motion = [e for e in events if e["type"] == "motion" and e["segment_id"] == i]
        direction = next(e["data"] for e in events if e["type"] == "text" and e["segment_id"] == i)
        assert [e["data"]["segment_time_s"] for e in motion] == [0, 0.04, 0.08]
        assert [e["sample_offset"] for e in motion] == [i * 2880 + j * 960 for j in range(3)]
        assert all(e["data"]["actions"] == direction["actions"] for e in motion)


def test_legacy_intent_gets_a_clip_but_explicit_stillness_does_not():
    fields = {
        "turn_id": "legacy",
        "segment_id": 0,
        "sequence": 0,
        "text": "好的。",
        "action_intent": "acknowledge",
    }
    assert Segment(**fields).actions[0].name == "nod"
    assert Segment(**fields, actions=[]).actions == []
