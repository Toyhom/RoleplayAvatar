"""HTTP streaming parity with the WebSocket protocol, plus bounded agent controls."""

import asyncio
import json
from contextlib import suppress

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field

from .agents import AGENT_ROLES, ModelGateway
from .contracts import Contract, Delivery, SpeakRequest
from .conversations import client_identity
from .design import design_character
from .initiative import Presence
from .languages import Locale
from .models import DEFAULTS, agent_config, model_options


class DesignInput(Contract):
    description: str = Field(min_length=2, max_length=1500)
    locale: Locale = "zh-CN"


class DirectionInput(Contract):
    text: str = Field(min_length=1, max_length=300)
    persona: str = Field(default="", max_length=2400)


def backend_routes(store, characters, refresh, session_factory, initiative, running):
    router = APIRouter(prefix="/api")

    def client(request):
        token = client_identity(request)
        try:
            store.owner(token)
        except ValueError:
            raise HTTPException(403, "Initialize /api/conversations/client first") from None
        return token

    @router.get("/agents")
    def agents():
        result = []
        for name, item in AGENT_ROLES.items():
            config = agent_config(name)
            provider, model = config["backend"], config["model"]
            if name == "vision" and model_options("vision").get("adapter") != "api":
                provider = "local-worker"
                model = model_options("vision").get("repo", DEFAULTS["vision"][0])
            result.append({"name": name, **item, "provider": provider, "model": model})
        return result

    @router.post("/agents/character-design")
    async def design(payload: DesignInput):
        try:
            return await design_character(payload.description, locale=payload.locale)
        except (httpx.HTTPError, ValueError, RuntimeError):
            raise HTTPException(502, "Character design provider is unavailable") from None

    @router.post("/agents/voice-direction")
    async def direction(payload: DirectionInput):
        try:
            return await ModelGateway("voice_direction").structured(
                "你是语音导演。为这段日常对话选择自然的语气、语速与段末停顿，避免夸张。",
                payload.model_dump(),
                Delivery,
                max_tokens=180,
            )
        except (httpx.HTTPError, ValueError, RuntimeError):
            raise HTTPException(502, "Voice direction provider is unavailable") from None

    @router.post("/conversations/{cid}/initiative/check")
    async def proactive(cid: str, request: Request, presence: Presence):
        refresh()
        token = client(request)
        try:
            value = store.get(token, cid)
            character = characters[value["character_id"]]
        except (ValueError, KeyError):
            raise HTTPException(404, "Unknown conversation or character") from None
        try:
            return await initiative.check(token, cid, character, presence)
        except (httpx.HTTPError, ValueError, RuntimeError):
            raise HTTPException(502, "Initiative model is unavailable") from None

    @router.post(
        "/turns",
        responses={
            200: {
                "description": "Streaming protocol events",
                "content": {"application/x-ndjson": {"schema": {"type": "string"}}},
            }
        },
    )
    async def turn(request: Request, payload: SpeakRequest):
        refresh()
        token = client(request)
        if not payload.conversation_id:
            raise HTTPException(422, "conversation_id is required for HTTP turns")
        queue = asyncio.Queue(maxsize=32)

        async def send(event):
            await queue.put(event)

        session = session_factory(send, token)
        key = (token, payload.turn_id)
        if key in running:
            raise HTTPException(409, "Turn is already running")
        try:
            await session.start(payload)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        running[key] = session

        async def events():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), 0.5)
                    except TimeoutError:
                        if session.task is None or session.task.done():
                            break
                        continue
                    yield json.dumps(event, ensure_ascii=False) + "\n"
                    if event["type"] in {"turn_end", "error", "cancelled"}:
                        break
            finally:
                with suppress(Exception):
                    await session.cancel(notify=False)
                running.pop(key, None)

        return StreamingResponse(
            events(),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    @router.post("/turns/{turn_id}/cancel")
    async def cancel(turn_id: str, request: Request):
        token = client(request)
        session = running.get((token, turn_id))
        if session:
            await session.cancel(turn_id)
        return {"cancelled": bool(session), "turn_id": turn_id}

    return router
