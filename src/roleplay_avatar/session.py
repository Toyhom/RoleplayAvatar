"""One cancellable producer per websocket; audio sample offsets are turn-relative."""

import asyncio
import base64
import logging
from contextlib import aclosing, suppress

from .adapters import CreatureAdapter, FixtureLLM, HumanoidAdapter, ToneReplayTTS, supported_style
from .contracts import CharacterPackage, Event, SpeakRequest
from .performance import combine_face

logger = logging.getLogger(__name__)


class Session:
    def __init__(
        self,
        send,
        characters: dict[str, CharacterPackage],
        tts=None,
        llm=None,
        mode="diagnostic_tone",
        audio_face=None,
        conversations=None,
        client_id=None,
        initiative=None,
    ):
        self.send = send
        self.characters = characters
        self.tts = tts or ToneReplayTTS()
        self.llm = llm or FixtureLLM()
        self.mode = mode
        self.audio_face = audio_face
        self.task = None
        self.turn_id = None
        self.sequence = 0
        self.sample_offset = 0
        self.segment_id = 0
        self.used_ids = set()
        self.conversations = conversations
        self.client_id = client_id
        self.conversation_id = None
        self.history = None
        self.initiative = initiative

    async def emit(self, kind, data=None):
        event = Event(
            type=kind,
            turn_id=self.turn_id,
            conversation_id=self.conversation_id,
            sequence=self.sequence,
            sample_offset=self.sample_offset,
            segment_id=self.segment_id,
            data=data or {},
        )
        self.sequence += 1
        await self.send(event.model_dump())

    async def cancel(self, turn_id=None, notify=True):
        if turn_id is not None and turn_id != self.turn_id:
            return  # a stale cancel must not affect the replacement turn
        if self.task is not None and not self.task.done():
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            if self.conversation_id:
                self.conversations.finish(self.client_id, self.conversation_id, self.turn_id, "interrupted")
            if notify:
                await self.emit("cancelled", {"next_state": "listen"})
        self.task = None

    async def start(self, request: SpeakRequest):
        if request.character_id not in self.characters:
            raise ValueError("unknown character_id")
        if request.turn_id in self.used_ids:
            raise ValueError("turn_id must be unique within a connection")
        if len(self.used_ids) >= 10000:
            raise ValueError("connection turn limit reached; reconnect")
        if request.conversation_id:
            if not self.conversations or not self.client_id:
                raise ValueError("Conversation client is not initialized")
            self.conversations.get(self.client_id, request.conversation_id, request.character_id)
        if request.source == "initiative":
            if not request.conversation_id or not self.initiative:
                raise ValueError("Initiative controller required")
            topic = self.initiative.consume(
                self.client_id, request.conversation_id, request.initiative_ticket
            )
            request = request.model_copy(update={"text": topic})
        await self.cancel()
        history = None
        if request.conversation_id:
            history = self.conversations.begin(
                self.client_id,
                request.conversation_id,
                request.character_id,
                request.turn_id,
                request.text,
                request.source,
            )
        self.conversation_id = request.conversation_id
        self.history = history
        self.turn_id = request.turn_id
        self.used_ids.add(request.turn_id)
        self.sequence = self.sample_offset = self.segment_id = 0
        self.task = asyncio.create_task(self.run(request))

    async def run(self, request):
        try:
            character = self.characters[request.character_id]
            streams = character.capabilities.active_streams
            driver = (
                HumanoidAdapter() if character.capabilities.controller == "humanoid" else CreatureAdapter()
            )
            await self.emit(
                "turn_start",
                {
                    "active_streams": streams,
                    "mode": self.mode,
                    "character_id": request.character_id,
                    "source": request.source,
                },
            )
            for stream in streams:
                await self.emit("stream_start", {"stream": stream})
            arguments = {"history": self.history} if self.history is not None else {}
            if request.source != "user":
                arguments["source"] = request.source
            async with aclosing(
                self.llm.stream(request.turn_id, request.text, character, **arguments)
            ) as segments:
                async for segment in segments:
                    if request.emotion != "auto":
                        segment = segment.model_copy(update={"emotion": request.emotion})
                    self.segment_id = segment.segment_id
                    if self.conversation_id:
                        self.conversations.append(
                            self.client_id, self.conversation_id, self.turn_id, segment.model_dump()
                        )
                    await self.emit(
                        "text", {**segment.model_dump(), "style": supported_style(segment.emotion, character)}
                    )
                    segment_start = self.sample_offset
                    next_chunk_offset = 0
                    async with aclosing(self.tts.stream(segment, character)) as raw_chunks:
                        directed = (
                            self.audio_face.annotate(raw_chunks)
                            if self.audio_face and "face" in streams
                            else raw_chunks
                        )
                        async with aclosing(directed) as chunks:
                            async for chunk in chunks:
                                if (
                                    chunk.sample_rate != 24000
                                    or len(chunk.pcm_s16le) % 2
                                    or chunk.sample_count == 0
                                    or chunk.sample_offset != next_chunk_offset
                                ):
                                    raise ValueError("TTS must emit contiguous mono PCM16 at 24000 Hz")
                                self.sample_offset = segment_start + chunk.sample_offset
                                await self.emit(
                                    "audio",
                                    {
                                        "encoding": "pcm_s16le",
                                        "channels": 1,
                                        "sample_count": chunk.sample_count,
                                        "pcm_base64": base64.b64encode(chunk.pcm_s16le).decode("ascii"),
                                    },
                                )
                                frame = driver.frame(character, segment, chunk)
                                await self.emit("motion", frame)
                                if "face" in streams:
                                    energy = min(1, frame["dry_rms"] / 0.09)
                                    values = {
                                        channel.target: min(
                                            channel.maximum,
                                            max(
                                                channel.minimum,
                                                energy * 0.65
                                                if channel.source == "jaw_open"
                                                else segment.intensity
                                                if channel.source == segment.emotion
                                                else 0,
                                            ),
                                        )
                                        for channel in character.face_map.channels
                                        if channel.source != "blink"
                                    }
                                    if chunk.face_coefficients is not None:
                                        fused = combine_face(
                                            chunk.face_coefficients, segment.emotion, segment.intensity
                                        )
                                        values = {
                                            channel.target: max(
                                                channel.minimum,
                                                min(channel.maximum, fused.get(channel.source, 0)),
                                            )
                                            for channel in character.face_map.channels
                                            if channel.source != "blink"
                                        }
                                    await self.emit(
                                        "face",
                                        {
                                            "values": values,
                                            "driver": "unitalker+director"
                                            if chunk.face_coefficients is not None
                                            else "energy_rhythm",
                                            "audio_coefficients": chunk.face_coefficients,
                                            "expression": segment.emotion,
                                            "intensity": segment.intensity,
                                            "action": segment.action_intent,
                                        },
                                    )
                                next_chunk_offset += chunk.sample_count
                                self.sample_offset += chunk.sample_count
            for stream in streams:
                await self.emit("stream_end", {"stream": stream})
            if self.conversation_id:
                self.conversations.finish(self.client_id, self.conversation_id, self.turn_id, "complete")
            await self.emit("turn_end", {"total_samples": self.sample_offset})
        except asyncio.CancelledError:
            if self.conversation_id:
                self.conversations.finish(self.client_id, self.conversation_id, self.turn_id, "interrupted")
            raise
        except Exception as exc:
            if self.conversation_id:
                self.conversations.finish(self.client_id, self.conversation_id, self.turn_id, "failed")
            logger.exception("Turn producer failed: %s", request.turn_id)
            # Do not send paths, model credentials or stack traces over the wire.
            await self.emit("error", {"code": "producer_failed", "exception_type": type(exc).__name__})
