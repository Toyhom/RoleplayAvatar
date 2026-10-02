"""Durable per-browser, per-character conversations; model history is server-owned."""

import hashlib
import json
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import Response as DownloadResponse
from pydantic import Field

from .contracts import Contract, Identifier

COOKIE = "avatar_client"


class NewConversation(Contract):
    character_id: Identifier
    title: str = Field(default="新对话", min_length=1, max_length=80)


class ConversationStore:
    def __init__(self, root):
        self.root = Path(root) / "outputs/conversations"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.active = {}

    def owner(self, value):
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
            raise ValueError("Conversation client is missing")
        return hashlib.sha256(value.encode()).hexdigest()

    def path(self, client, cid):
        if not re.fullmatch(r"[a-f0-9]{32}", cid):
            raise ValueError("Invalid conversation ID")
        return self.root / self.owner(client) / (cid + ".json")

    def write(self, client, value):
        path = self.path(client, value["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def get(self, client, cid, character_id=None):
        with self.lock:
            path = self.path(client, cid)
            if not path.is_file():
                raise ValueError("Unknown conversation")
            value = json.loads(path.read_text())
            if character_id is not None and value["character_id"] != character_id:
                raise ValueError("Conversation belongs to a different character")
            # A Web process restart cannot leave a phantom in-progress turn.
            if (self.owner(client), cid) not in self.active:
                changed = False
                for message in value["messages"]:
                    if message.get("status") == "streaming":
                        message["status"] = "interrupted"
                        changed = True
                if changed:
                    self.write(client, value)
            return value

    @staticmethod
    def has_content(value):
        return any(m["role"] == "user" and any(c.isalnum() for c in m["content"]) for m in value["messages"])

    def create(self, client, character_id, title="新对话"):
        with self.lock:
            # Reuse an untouched thread, including concurrent create requests.
            for row in self.list(client, character_id):
                previous = self.get(client, row["id"])
                if not self.has_content(previous):
                    return previous
            now = time.time()
            value = {
                "id": uuid.uuid4().hex,
                "character_id": character_id,
                "title": title,
                "created_at": now,
                "updated_at": now,
                "messages": [],
                "initiative": {"enabled": False, "idle_seconds": 35, "cooldown_seconds": 120},
            }
            self.write(client, value)
            return value

    def list(self, client, character_id):
        with self.lock:
            folder = self.root / self.owner(client)
            rows = [self.get(client, p.stem) for p in folder.glob("*.json")]
            rows = [r for r in rows if r["character_id"] == character_id]
            return [
                {**{k: v for k, v in r.items() if k != "messages"}, "has_content": self.has_content(r)}
                for r in sorted(rows, key=lambda r: r["updated_at"], reverse=True)
            ]

    def history(self, value):
        # Only completed pairs enter model context. Partial/interrupted replies
        # remain visible to the user and cannot silently become completed facts.
        completed = {
            m["turn_id"] for m in value["messages"] if m["role"] == "assistant" and m["status"] == "complete"
        }
        result = []
        for message in value["messages"]:
            if message["turn_id"] not in completed:
                continue
            content = (
                message["content"]
                if message["role"] == "user"
                else "\n".join(json.dumps(s, ensure_ascii=False) for s in message["segments"])
            )
            result.append({"role": message["role"], "content": content})
        return result[-10:]

    def begin(self, client, cid, character_id, turn_id, text, source="user"):
        with self.lock:
            value = self.get(client, cid, character_id)
            key = (self.owner(client), cid)
            if key in self.active:
                raise ValueError("Conversation already has an active response")
            if any(m["turn_id"] == turn_id for m in value["messages"]):
                raise ValueError("turn_id must be unique within a conversation")
            history = self.history(value)
            if source == "user" and not self.has_content(value) and value["title"] == "新对话":
                value["title"] = text[:24]
            now = time.time()
            if source == "user":
                value["messages"].append(
                    {
                        "role": "user",
                        "content": text,
                        "turn_id": turn_id,
                        "status": "complete",
                        "created_at": now,
                    }
                )
            value["messages"] += [
                {
                    "role": "assistant",
                    "content": "",
                    "segments": [],
                    "turn_id": turn_id,
                    "status": "streaming",
                    "source": source,
                    "created_at": now,
                },
            ]
            value["updated_at"] = time.time()
            self.write(client, value)
            self.active[key] = turn_id
            return history

    def append(self, client, cid, turn_id, segment):
        with self.lock:
            value = self.get(client, cid)
            if self.active.get((self.owner(client), cid)) != turn_id:
                raise ValueError("Stale conversation writer")
            message = value["messages"][-1]
            direction = {
                k: v
                for k, v in segment.items()
                if k in {"text", "emotion", "intensity", "action_intent", "actions", "delivery"}
            }
            message["segments"].append(direction)
            message["content"] += ("\n\n" if message["content"] else "") + direction["text"]
            value["updated_at"] = time.time()
            self.write(client, value)

    def finish(self, client, cid, turn_id, status):
        with self.lock:
            key = (self.owner(client), cid)
            if self.active.get(key) != turn_id:
                return
            value = self.get(client, cid)
            value["messages"][-1]["status"] = status
            value["updated_at"] = time.time()
            self.write(client, value)
            self.active.pop(key, None)


class InitiativeSettings(Contract):
    enabled: bool = False
    idle_seconds: int = Field(default=35, ge=10, le=600)
    cooldown_seconds: int = Field(default=120, ge=30, le=3600)


def client_identity(request):
    return request.cookies.get(COOKIE) or request.headers.get("x-avatar-client")


def conversation_routes(store, characters, refresh):
    router = APIRouter(prefix="/api/conversations")

    def client(request):
        token = client_identity(request)
        try:
            store.owner(token)
        except ValueError:
            raise HTTPException(403, "Conversation client is not initialized") from None
        return token

    @router.post("/client")
    def initialize(request: Request, response: Response):
        token = client_identity(request)
        try:
            store.owner(token)
        except ValueError:
            token = uuid.uuid4().hex
        response.set_cookie(
            COOKIE,
            token,
            max_age=365 * 24 * 3600,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
        )
        return {"ready": True, "client_id": token}

    @router.get("")
    def listing(request: Request, character_id: str):
        refresh()
        if character_id not in characters:
            raise HTTPException(404, "Unknown character")
        return store.list(client(request), character_id)

    @router.post("", status_code=201)
    def create(request: Request, payload: NewConversation):
        refresh()
        if payload.character_id not in characters:
            raise HTTPException(404, "Unknown character")
        return store.create(client(request), payload.character_id, payload.title)

    @router.get("/{cid}/export")
    def export(request: Request, cid: str):
        try:
            value = store.get(client(request), cid)
        except ValueError:
            raise HTTPException(404, "Unknown conversation") from None
        export = {"schema_version": "1.0", "exported_at": time.time(), "conversation": value}
        return DownloadResponse(
            json.dumps(export, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="conversation-{cid}.json"'},
        )

    @router.patch("/{cid}/initiative")
    def configure_initiative(request: Request, cid: str, payload: InitiativeSettings):
        try:
            with store.lock:
                value = store.get(client(request), cid)
                value["initiative"] = payload.model_dump()
                value["updated_at"] = time.time()
                store.write(client(request), value)
                return value["initiative"]
        except ValueError:
            raise HTTPException(404, "Unknown conversation") from None

    @router.get("/{cid}")
    def details(request: Request, cid: str):
        try:
            return store.get(client(request), cid)
        except ValueError:
            raise HTTPException(404, "Unknown conversation") from None

    return router
