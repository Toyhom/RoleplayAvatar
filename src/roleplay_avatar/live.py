"""Async adapters to isolated GPU services; cancellation closes the actual streaming requests."""

import base64
import json
import unicodedata

import httpx

from .adapters import AudioChunk
from .agents import ModelGateway
from .contracts import STATES, ActionCue, Delivery, Segment
from .models import prompt_text

DIRECTOR = prompt_text("performance")


class PerformanceParser:
    """Incrementally decode complete objects. Never send control syntax to speech."""

    def __init__(self):
        self.buffer = ""

    def feed(self, text):
        self.buffer += text
        if len(self.buffer) > 16000:
            raise ValueError("Structured reply exceeded its limit")
        result = []
        decoder = json.JSONDecoder()
        while "{" in self.buffer:
            self.buffer = self.buffer[self.buffer.index("{") :]
            try:
                value, length = decoder.raw_decode(self.buffer)
            except json.JSONDecodeError:
                break
            self.buffer = self.buffer[length:]
            if not isinstance(value, dict) or not isinstance(value.get("text"), str):
                continue
            spoken = value["text"].strip()
            if not spoken or len(spoken) > 300:
                continue
            emotion = value.get("emotion", "neutral")
            if not isinstance(emotion, str) or emotion not in {"neutral", "happy", "sad", "angry", "soft"}:
                emotion = "neutral"
            action = value.get("action_intent", "speak")
            if not isinstance(action, str) or action not in STATES:
                action = "speak"
            intensity = value.get("intensity", 0.4)
            if not isinstance(intensity, (int, float)) or not 0 <= intensity <= 1:
                intensity = 0.4
            performance = {
                "text": spoken,
                "emotion": emotion,
                "intensity": intensity,
                "action_intent": action,
            }
            if "delivery" in value:
                try:
                    performance["delivery"] = Delivery.model_validate(value["delivery"]).model_dump()
                except ValueError:
                    pass
            if "actions" in value:
                actions = []
                for cue in value["actions"][:3] if isinstance(value["actions"], list) else []:
                    try:
                        actions.append(ActionCue.model_validate(cue).model_dump())
                    except ValueError:
                        continue  # Never execute unknown or unbounded model controls.
                performance["actions"] = actions
            result.append(performance)
        return result


class RemoteLLM:
    """Dialogue agent; the same gateway is used by the initiative and design agents."""

    def __init__(self, url=None):
        self.gateway = ModelGateway("roleplay", url)
        self.histories = {}

    async def stream(self, turn_id, text, character, history=None, source="user"):
        history = (
            self.histories.setdefault(character.profile.character_id, []) if history is None else history
        )
        messages = list(history[-16:])
        mode = self.gateway.config.get("output_mode", "performance")
        persona = character.profile.persona + "\n" + prompt_text("roleplay")
        persona += "\n" + (prompt_text("actor") if mode == "actor_director" else prompt_text("performance"))
        if source == "initiative":
            persona += (
                "\n本轮由主动交互控制器触发，不是用户的新消息。自然开启以下话题，不声称用户刚才说过它："
                + text
            )
            if not messages:
                messages = [{"role": "user", "content": "开始见面。"}]
        else:
            messages.append({"role": "user", "content": text})
        gateway = self.gateway
        actor_text = None
        if mode == "actor_director":
            # Convert stored performance records to readable dialogue for the actor.
            actor_messages = []
            for message in messages:
                content = message["content"]
                if message["role"] == "assistant":
                    parsed = PerformanceParser().feed(content)
                    if parsed:
                        content = "\n".join(
                            p["text"] + "".join(" (" + cue["name"] + ")" for cue in p.get("actions", []))
                            for p in parsed
                        )
                actor_messages.append({"role": message["role"], "content": content})
            actor_text = ""
            async for token in gateway.stream(persona, actor_messages, max_tokens=700):
                actor_text += token
                if len(actor_text) > 16000:
                    raise ValueError("Actor reply exceeded its limit")
            if not actor_text.strip():
                raise ValueError("Actor returned an empty reply")
            gateway = ModelGateway("performance_director")
            persona = prompt_text("performance") + "\n" + prompt_text("performance_director")
            messages = [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "persona": character.profile.persona,
                            "user_message": text,
                            "actor_reply": actor_text,
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        elif mode != "performance":
            raise ValueError(f"Unknown roleplay output_mode: {mode}")
        full = []
        for attempt in range(2):
            parser = PerformanceParser()
            raw = []
            async for token in gateway.stream(persona, messages, max_tokens=1400):
                raw.append(token)
                for performance in parser.feed(token):
                    if len(full) >= 4:
                        continue
                    index = len(full)
                    full.append(performance)
                    yield Segment(turn_id=turn_id, segment_id=index, sequence=index, **performance)
            if full:
                if source == "user":
                    history.append({"role": "user", "content": text})
                history.append(
                    {
                        "role": "assistant",
                        "content": "\n".join(json.dumps(p, ensure_ascii=False) for p in full),
                    }
                )
                del history[:-16]
                return
            if attempt == 0:
                messages += [
                    {"role": "assistant", "content": "".join(raw)[:3000]},
                    {
                        "role": "user",
                        "content": "请按系统要求改写成逐行JSON，保留原意，补齐text、emotion、intensity、action_intent、actions。",
                    },
                ]
        raise ValueError("The roleplay model did not return a valid performance response")


class RemoteTTS:
    def __init__(self, url):
        self.url = url.rstrip("/")

    async def stream(self, segment, character):
        # Preserve the original reply in text events, but do not send emoji or
        # symbol-only fragments to a speech model (which can produce zero tokens).
        speech_text = "".join(c for c in segment.text if unicodedata.category(c) not in {"So", "Sk", "Cf"})
        if not any(c.isalnum() for c in speech_text):
            return
        style = segment.emotion if segment.emotion in character.voice_profile.supported_styles else "neutral"
        payload = {
            "character_id": character.profile.character_id,
            "text": speech_text,
            "style": style,
            "intensity": segment.intensity,
            "delivery": segment.delivery.model_dump(),
        }
        expected = 0
        ended = False
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120, connect=5)) as client:  # noqa: SIM117
            async with client.stream("POST", self.url + "/speak", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    item = json.loads(line)
                    if "error" in item:
                        raise RuntimeError("TTS inference failed: " + item["error"])
                    if item.get("done"):
                        if item["total_samples"] != expected:
                            raise ValueError("TTS completion sample count mismatch")
                        ended = True
                        continue
                    if item["sample_rate"] != 24000 or item["sample_offset"] != expected:
                        raise ValueError("TTS audio is not contiguous 24 kHz")
                    pcm = base64.b64decode(item["pcm_base64"], validate=True)
                    if len(pcm) != item["sample_count"] * 2:
                        raise ValueError("TTS PCM length mismatch")
                    # Subdivide each newly available model block for 25 fps performance control.
                    # This is still consumed before the remaining sentence has been synthesized.
                    for offset in range(0, len(pcm), 1920):
                        piece = pcm[offset : offset + 1920]
                        yield AudioChunk(piece, expected)
                        expected += len(piece) // 2
        if not ended or expected == 0:
            raise RuntimeError("TTS stream ended without a complete nonempty utterance")

        pause_samples = int(segment.delivery.pause_after_ms * 24)
        for offset in range(0, pause_samples, 960):
            count = min(960, pause_samples - offset)
            yield AudioChunk(b"\0\0" * count, expected + offset)
