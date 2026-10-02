"""Loopback-only by launcher default; assets are loaded from this checkout."""

import asyncio
import json
import os
import secrets
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .assets import catalog, cubism_files, inside
from .backend import backend_routes
from .contracts import CancelRequest, SpeakRequest
from .conversations import ConversationStore, client_identity, conversation_routes
from .initiative import InitiativeController
from .live import RemoteLLM, RemoteTTS
from .models import agent_config
from .performance import RemoteAudioFace
from .session import Session
from .speech_input import speech_routes
from .studio import studio_routes


def create_app(project_root=None, mode=None, headless=None):
    root = Path(project_root or os.environ.get("AVATAR_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
    mode = mode or os.environ.get("AVATAR_MODE", "live")
    headless = os.environ.get("AVATAR_HEADLESS", "0") == "1" if headless is None else headless
    api_key = os.environ.get("AVATAR_API_KEY")
    character_root = root / ("fixtures/characters_m0" if mode == "replay" else "characters")
    characters = {}

    def refresh():
        found = catalog(character_root)
        if mode == "live" and os.environ.get("AVATAR_HIDE_LEGACY", "0") == "1":
            found = {k: v for k, v in found.items() if not k.endswith("_demo")}
        characters.update(found)
        for key in list(characters):
            if key not in found:
                characters.pop(key, None)

    refresh()
    if mode not in {"live", "replay"}:
        raise ValueError("AVATAR_MODE must be live or replay")
    llm_config = agent_config("roleplay")
    llm_url = llm_config["url"].rstrip("/")
    tts_url = os.environ.get("AVATAR_TTS_URL", "http://127.0.0.1:18120")
    app = FastAPI(title="Roleplay Avatar", version="0.2.0")
    app.include_router(studio_routes(root, refresh))
    app.include_router(speech_routes())
    conversations = ConversationStore(root)
    app.include_router(conversation_routes(conversations, characters, refresh))
    initiative = InitiativeController(conversations)
    running = {}

    def session_factory(send, client_id):
        return Session(
            send,
            characters,
            tts=RemoteTTS(tts_url) if mode == "live" else None,
            llm=RemoteLLM() if mode == "live" else None,
            mode=mode,
            audio_face=RemoteAudioFace(os.environ["AVATAR_AUDIO_FACE_URL"])
            if mode == "live" and os.environ.get("AVATAR_AUDIO_FACE_URL")
            else None,
            conversations=conversations,
            client_id=client_id,
            initiative=initiative,
        )

    app.state.conversations = conversations
    app.state.initiative = initiative
    app.include_router(
        backend_routes(conversations, characters, refresh, session_factory, initiative, running)
    )

    @app.middleware("http")
    async def same_origin(request, call_next):
        if api_key and not secrets.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + api_key
        ):
            return JSONResponse({"detail": "API key required"}, status_code=401)
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin
            not in {f"http://{request.headers.get('host')}", f"https://{request.headers.get('host')}"}
        ):
            return JSONResponse({"detail": "cross-origin write rejected"}, status_code=403)
        return await call_next(request)

    @app.get("/healthz")
    def health():
        return {
            "status": "ok",
            "mode": "live" if mode == "live" else "diagnostic_tone",
            "gpu_required": mode == "live",
            "headless": headless,
        }

    @app.get("/api/services")
    async def services():
        async with httpx.AsyncClient(trust_env=False, timeout=3) as client:

            async def probe(url, openai=False):
                try:
                    key = (
                        os.environ.get(llm_config.get("api_key_env", "AVATAR_LLM_API_KEY"))
                        if openai
                        else None
                    )
                    headers = {"Authorization": "Bearer " + key} if key else {}
                    if openai and llm_config["backend"] == "anthropic":
                        headers = {"anthropic-version": "2023-06-01", **({"x-api-key": key} if key else {})}
                    response = await client.get(url + ("/models" if openai else "/healthz"), headers=headers)
                    response.raise_for_status()
                    return {"status": "ready"} if openai else response.json()
                except (httpx.HTTPError, ValueError):
                    return {"status": "unavailable"}

            llm, tts = await asyncio.gather(probe(llm_url, llm_config["backend"] != "local"), probe(tts_url))
            audio_face = (
                await probe(os.environ["AVATAR_AUDIO_FACE_URL"])
                if os.environ.get("AVATAR_AUDIO_FACE_URL")
                else {"status": "disabled"}
            )
            asr = (
                await probe(os.environ["AVATAR_ASR_URL"])
                if os.environ.get("AVATAR_ASR_URL")
                else {"status": "disabled"}
            )
        return {"mode": mode, "llm": llm, "tts": tts, "audio_face": audio_face, "asr": asr}

    def preview_url(cid):
        for filename in ("concept.png", "preview.png"):
            if (character_root / cid / filename).is_file():
                return f"/assets/{cid}/{filename}"
        return None

    @app.get("/api/characters")
    def list_characters():
        refresh()
        return [
            {
                "profile": c.profile.model_dump(),
                "capabilities": c.capabilities.model_dump(),
                "provenance": c.provenance.model_dump(),
                "preview_url": preview_url(c.profile.character_id),
            }
            for c in list(characters.values())
        ]

    @app.get("/api/characters/{character_id}")
    def character(character_id: str):
        refresh()
        if character_id not in characters:
            raise HTTPException(404, "unknown character_id")
        return {**characters[character_id].model_dump(), "preview_url": preview_url(character_id)}

    @app.get("/assets/{character_id}/{filename}")
    def asset(character_id: str, filename: str):
        refresh()
        if character_id not in characters or filename not in {
            "model.glb",
            "reference.wav",
            "concept.png",
            "preview.png",
        }:
            raise HTTPException(404, "unknown asset")
        path = (
            root
            / "characters"
            / character_id
            / (
                characters[character_id].voice_profile.reference_audio
                if filename == "reference.wav"
                else filename
            )
        )
        if not path.is_file():
            raise HTTPException(404, "asset is not prepared")
        return FileResponse(path)

    @app.get("/assets/{character_id}/puppet/{filename}")
    def puppet_asset(character_id: str, filename: str):
        refresh()
        if character_id not in characters or filename not in {"portrait.png", "rig.json", "mouth-atlas.png"}:
            raise HTTPException(404, "unknown puppet asset")
        try:
            path = inside(character_root / character_id, "puppet/" + filename)
        except ValueError:
            raise HTTPException(404, "invalid puppet path") from None
        if not path.is_file():
            raise HTTPException(404, "puppet is not prepared")
        return FileResponse(path)

    @app.get("/vendor/cubism-core.js")
    def cubism_core():
        path = root / "third_party/cubism/core.js"
        if not path.is_file():
            raise HTTPException(404, "Optional Cubism Core is not installed")
        return FileResponse(path, media_type="application/javascript")

    @app.get("/assets/{character_id}/live2d/{filename:path}")
    def cubism_asset(character_id: str, filename: str):
        refresh()
        character = characters.get(character_id)
        if not character or character.profile.renderer_2d != "cubism":
            raise HTTPException(404, "unknown Cubism character")
        folder = character_root / character_id
        relative = "live2d/" + filename
        try:
            if relative not in cubism_files(folder, character.profile.live2d_model):
                raise ValueError("undeclared asset")
            path = inside(folder, relative)
        except (ValueError, OSError):
            raise HTTPException(404, "unknown Cubism asset") from None
        if not path.is_file():
            raise HTTPException(404, "asset is not prepared")
        return FileResponse(path)

    @app.websocket("/ws")
    async def websocket(ws: WebSocket):
        # Permit non-browser test clients; browser connections must be same-origin.
        origin = ws.headers.get("origin")
        if origin and origin not in {f"http://{ws.headers.get('host')}", f"https://{ws.headers.get('host')}"}:
            await ws.close(code=1008)
            return
        await ws.accept()
        if api_key and not secrets.compare_digest(ws.headers.get("authorization", ""), "Bearer " + api_key):
            await ws.close(code=1008)
            return
        token = client_identity(ws)
        session = session_factory(ws.send_json, token)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    if len(raw) > 8192:
                        raise ValueError("request too large")
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise TypeError("object required")
                    if data.get("type") == "speak":
                        refresh()
                        request = SpeakRequest.model_validate(data)
                        await session.start(request)
                        key = (token, request.turn_id)
                        running[key] = session
                        session.task.add_done_callback(lambda _, key=key: running.pop(key, None))
                    else:
                        request = CancelRequest.model_validate(data)
                        await session.cancel(request.turn_id)
                except (TypeError, ValueError, ValidationError):
                    await ws.send_json({"type": "request_error", "code": "invalid_request"})
        except WebSocketDisconnect:
            pass
        finally:
            await session.cancel(notify=False)

    @app.get("/")
    def index():
        if headless:
            return {
                "service": "roleplay-avatar",
                "docs": "/docs",
                "openapi": "/openapi.json",
                "transport": ["HTTP NDJSON", "WebSocket"],
            }
        return FileResponse(root / "web" / "index.html")

    if not headless:
        app.mount("/static", StaticFiles(directory=root / "web"), name="static")
    return app
