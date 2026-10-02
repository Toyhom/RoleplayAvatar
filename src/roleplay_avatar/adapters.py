"""CPU fixtures and model-facing protocols; no model weights are loaded here."""

import asyncio
import math
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from .contracts import CharacterPackage, Segment

SAMPLE_RATE = 24000


@dataclass(frozen=True)
class AudioChunk:
    pcm_s16le: bytes
    sample_offset: int  # relative to the segment
    sample_rate: int = SAMPLE_RATE
    face_coefficients: dict[str, float] | None = None

    @property
    def sample_count(self) -> int:
        return len(self.pcm_s16le) // 2


class TTSAdapter(Protocol):
    def stream(self, segment: Segment, character: CharacterPackage) -> AsyncIterator[AudioChunk]: ...


class LLMAdapter(Protocol):
    def stream(
        self, turn_id: str, text: str, character: CharacterPackage, history=None, source="user"
    ) -> AsyncIterator[Segment]: ...


class FixtureLLM:
    """Fixed diagnostic response. This is not roleplay inference."""

    async def stream(self, turn_id: str, text: str, character: CharacterPackage, history=None, source="user"):
        for index, sentence in enumerate(
            [
                f"{character.profile.display_name}的接口回放已开始。",
                f"收到输入：{text}。",
                "现在可以打断，检查旧轮音频是否停止。",
            ]
        ):
            yield Segment(
                turn_id=turn_id,
                segment_id=index,
                sequence=index,
                text=sentence,
                action_intent="acknowledge" if index == 0 else "speak",
            )


class ToneReplayTTS:
    """Generate a diagnostic tone incrementally. It is not speech or a TTS benchmark."""

    def __init__(self, chunk_samples=2400, duration_samples=24000, paced=True):
        self.chunk_samples = chunk_samples
        self.duration_samples = duration_samples
        self.paced = paced

    async def stream(self, segment: Segment, character: CharacterPackage):
        frequency = {"humanoid": 330, "quadruped": 165}.get(character.capabilities.body_topology, 440)
        for offset in range(0, self.duration_samples, self.chunk_samples):
            count = min(self.chunk_samples, self.duration_samples - offset)
            values = []
            for sample in range(offset, offset + count):
                envelope = min(1, sample / 480, (self.duration_samples - sample - 1) / 480)
                values.append(
                    round(3500 * envelope * math.sin(2 * math.pi * frequency * sample / SAMPLE_RATE))
                )
            yield AudioChunk(struct.pack(f"<{count}h", *values), offset)
            await asyncio.sleep(count / SAMPLE_RATE if self.paced else 0)


def supported_style(style: str, character: CharacterPackage) -> str:
    return style if style in character.voice_profile.supported_styles else "neutral"


class CreatureAdapter:
    """Small, bounded rest-relative rotations. No retargeting or phoneme lip sync."""

    def frame(self, character: CharacterPackage, segment: Segment, chunk: AudioChunk) -> dict:
        samples = struct.unpack(f"<{chunk.sample_count}h", chunk.pcm_s16le)
        rms = math.sqrt(sum(v * v for v in samples) / max(1, len(samples))) / 32768
        energy = min(1, rms / 0.08)
        selected = segment.action_intent
        while character.motion_manifest.motions[selected].fallback:
            selected = character.motion_manifest.motions[selected].fallback
        procedure = character.motion_manifest.motions[selected].procedural
        rotations = {}
        for joint in character.rig_map.joints:
            angle = 0.0
            if (
                joint.semantic == "jaw"
                and joint.owner == "speech"
                and character.capabilities.face_mode == "jaw_only"
                and procedure != "neutral"
            ):
                angle = 12 * energy * segment.intensity
            elif (
                joint.semantic in {"head", "sensor"}
                and joint.owner == "expression"
                and procedure != "neutral"
            ):
                rhythm = math.sin(chunk.sample_offset / SAMPLE_RATE * math.pi)
                amplitude = {"acknowledge": 7, "explain": 4, "uncertain": 5, "alert": 6, "leave": 3}.get(
                    segment.action_intent, 3
                )
                angle = amplitude * segment.intensity * rhythm
            elif joint.semantic in {"wing", "tail", "arm", "antenna"} and joint.owner == "expression":
                angle = 5 * segment.intensity * math.sin(chunk.sample_offset / SAMPLE_RATE * 1.8)
            else:
                continue
            angle = max(joint.angle_limits_deg[0], min(joint.angle_limits_deg[1], angle))
            half = math.radians(angle) / 2
            rotations[joint.name] = [*(axis * math.sin(half) for axis in joint.local_axis), math.cos(half)]
        return {
            "motion_state": selected,
            "segment_id": segment.segment_id,
            "segment_time_s": chunk.sample_offset / SAMPLE_RATE,
            "actions": [cue.model_dump() for cue in segment.actions],
            "emotion": segment.emotion,
            "intensity": segment.intensity,
            "rotations_delta_xyzw": rotations,
            "dry_rms": rms,
            "face_driver": "energy_rhythm" if character.capabilities.face_mode == "jaw_only" else "none",
            "coordinate_system": character.rig_map.coordinate_system,
        }


class HumanoidAdapter(CreatureAdapter):
    """M0 neutral/rhythm fixture; DLP3D speech2motion/audio2face integration is M1."""
