import asyncio
import io
import json
import shutil
import stat
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from conftest import ROOT
from fastapi.testclient import TestClient
from PIL import Image

from roleplay_avatar.app import create_app
from roleplay_avatar.contracts import Profile, SpeakRequest
from roleplay_avatar.conversations import ConversationStore
from roleplay_avatar.initiative import InitiativeController, InitiativeDecision, Presence
from roleplay_avatar.models import agent_config, model_path
from roleplay_avatar.native_import import extract_live2d
from roleplay_avatar.voice_direction import synthesis_direction

CLIENT = "a" * 32


def test_empty_guard_is_atomic_and_does_not_count_initiative(tmp_path):
    store = ConversationStore(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: store.create(CLIENT, "avatar")["id"], range(20)))
    assert len(set(ids)) == 1
    cid = ids[0]
    store.begin(CLIENT, cid, "avatar", "greet", "hello", source="initiative")
    store.append(CLIENT, cid, "greet", {"text": "你好"})
    store.finish(CLIENT, cid, "greet", "complete")
    assert store.create(CLIENT, "avatar")["id"] == cid
    store.begin(CLIENT, cid, "avatar", "reply", "我叫小明")
    store.finish(CLIENT, cid, "reply", "complete")
    assert store.create(CLIENT, "avatar")["id"] != cid
    assert store.create(CLIENT, "another")["id"] != cid


def test_headless_http_export_ownership_and_key(tmp_path, monkeypatch):
    import roleplay_avatar.session as sessions
    from roleplay_avatar.adapters import ToneReplayTTS

    monkeypatch.setattr(sessions, "ToneReplayTTS", lambda: ToneReplayTTS(duration_samples=960, paced=False))
    shutil.copytree(ROOT / "fixtures", tmp_path / "fixtures")
    monkeypatch.setenv("AVATAR_API_KEY", "test-secret")
    app = create_app(tmp_path, mode="replay", headless=True)
    with TestClient(app) as client:
        assert client.get("/").status_code == 401
        client.headers["Authorization"] = "Bearer test-secret"
        assert client.get("/").json()["transport"] == ["HTTP NDJSON", "WebSocket"]
        assert client.get("/static/app.js").status_code == 404
        assert "/api/turns" in client.get("/openapi.json").json()["paths"]
        identity = client.post("/api/conversations/client").json()["client_id"]
        client.cookies.clear()
        client.headers["X-Avatar-Client"] = identity
        cid = client.post("/api/conversations", json={"character_id": "robot_demo"}).json()["id"]
        payload = {
            "type": "speak",
            "turn_id": "http1",
            "character_id": "robot_demo",
            "conversation_id": cid,
            "text": "你好",
        }
        response = client.post("/api/turns", json=payload)
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[0]["type"] == "turn_start" and events[-1]["type"] == "turn_end"
        assert any(e["type"] == "audio" for e in events)
        download = client.get(f"/api/conversations/{cid}/export")
        assert "attachment" in download.headers["content-disposition"]
        value = download.json()["conversation"]
        assert len(value["messages"]) == 2 and value["messages"][1]["segments"]
        assert value["messages"][1]["status"] == "complete"
        assert client.post("/api/turns", json=payload).status_code == 409
        client.headers["X-Avatar-Client"] = "b" * 32
        assert client.get(f"/api/conversations/{cid}/export").status_code == 404
        assert client.post("/api/turns/http1/cancel").json()["cancelled"] is False


def test_initiative_policy_ticket_and_context_race(tmp_path, characters):
    store = ConversationStore(tmp_path)
    cid = store.create(CLIENT, "robot_demo")["id"]
    calls = []

    class Gateway:
        async def structured(self, system, data, schema, **kwargs):
            calls.append(data)
            return InitiativeDecision(speak=True, reason="适合介绍", topic="聊聊你的花园")

    controller = InitiativeController(store, Gateway())

    def arm():
        value = store.get(CLIENT, cid)
        value.update(
            initiative={"enabled": True, "idle_seconds": 10, "cooldown_seconds": 30},
            updated_at=time.time() - 40,
        )
        store.write(CLIENT, value)
        controller.last_checks.clear()

    async def run():
        presence = Presence(idle_seconds=60)
        character = characters["robot_demo"]
        assert (await controller.check(CLIENT, cid, character, presence))["reason"] == "disabled"
        arm()
        for field in ["typing", "recording", "playing"]:
            result = await controller.check(
                CLIENT, cid, character, Presence(idle_seconds=60, **{field: True})
            )
            assert result["reason"] == "user_busy"
        assert not calls
        result = await controller.check(CLIENT, cid, character, presence)
        assert result["speak"] and result["ticket"]
        assert controller.consume(CLIENT, cid, result["ticket"]) == "聊聊你的花园"
        with pytest.raises(ValueError):
            controller.consume(CLIENT, cid, result["ticket"])
        assert (await controller.check(CLIENT, cid, character, presence))["reason"] == "cooldown"
        store.begin(CLIENT, cid, "robot_demo", "initiative1", "花园", source="initiative")
        store.append(CLIENT, cid, "initiative1", {"text": "我在种花"})
        store.finish(CLIENT, cid, "initiative1", "complete")
        arm()
        value = store.get(CLIENT, cid)
        value["last_initiative_at"] = 0
        store.write(CLIENT, value)
        assert (await controller.check(CLIENT, cid, character, presence))["reason"] == "awaiting_user"
        assert all(m["role"] == "assistant" for m in value["messages"])
        store.begin(CLIENT, cid, "robot_demo", "user1", "先别说话")
        store.finish(CLIENT, cid, "user1", "complete")
        arm()
        result = await controller.check(CLIENT, cid, character, presence)
        store.begin(CLIENT, cid, "robot_demo", "user2", "我回来了")
        with pytest.raises(ValueError, match="context changed"):
            controller.consume(CLIENT, cid, result["ticket"])
        store.finish(CLIENT, cid, "user2", "complete")
        arm()

        class RacingGateway:
            async def structured(self, *args, **kwargs):
                store.begin(CLIENT, cid, "robot_demo", "race", "我先说")
                return InitiativeDecision(speak=True, reason="介绍", topic="花园")

        controller.gateway = RacingGateway()
        assert (await controller.check(CLIENT, cid, character, presence))["reason"] == "context_changed"

    asyncio.run(run())


def zip_resources(extra=None, refs=None):
    texture = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(texture, format="PNG")
    data = {"Version": 3, "FileReferences": refs or {"Moc": "model.moc3", "Textures": ["tex.png"]}}
    files = {
        "model.model3.json": json.dumps(data).encode(),
        "model.moc3": b"MOC3\x00test",
        "tex.png": texture.getvalue(),
        "LICENSE.txt": b"user terms",
    }
    files.update(extra or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return output.getvalue()


def test_native_import_files_and_reference_boundaries(tmp_path):
    manifest, report = extract_live2d(zip_resources(), tmp_path / "good/live2d")
    assert manifest == "live2d/model.model3.json" and report["files"] == 3
    assert (tmp_path / "good/live2d/LICENSE.txt").read_text() == "user terms"
    for i, name in enumerate(["../evil.json", "/absolute.json", "code.js", "bad\\file.json"]):
        with pytest.raises(ValueError):
            extract_live2d(zip_resources({name: b"bad"}), tmp_path / f"bad{i}/live2d")
    with pytest.raises(ValueError):
        extract_live2d(
            zip_resources(refs={"Moc": "../private.moc3", "Textures": ["tex.png"]}),
            tmp_path / "escape/live2d",
        )
    with pytest.raises(ValueError):
        extract_live2d(zip_resources({"second.model3.json": b"{}"}), tmp_path / "multiple/live2d")
    symlink = zipfile.ZipInfo("link.json")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError):
        extract_live2d(zip_resources({symlink: b"target"}), tmp_path / "symlink/live2d")


def test_model_configuration_and_bounded_voice(tmp_path, monkeypatch):
    config = tmp_path / "models.json"
    config.write_text(
        json.dumps(
            {
                "models": {"roleplay": {"path": str(tmp_path / "custom")}},
                "agents": {
                    "default": {"backend": "openai", "url": "http://llm/v1"},
                    "initiative": {"model": "small-controller"},
                },
            }
        )
    )
    monkeypatch.setenv("AVATAR_MODELS_CONFIG", str(config))
    assert model_path("roleplay") == tmp_path / "custom"
    monkeypatch.setenv("AVATAR_ROLEPLAY_MODEL_PATH", str(tmp_path / "override"))
    assert model_path("roleplay") == tmp_path / "override"
    assert agent_config("initiative")["model"] == "small-controller"
    assert agent_config("roleplay")["backend"] == "openai"
    assert synthesis_direction("happy", 0.4, {}) is None
    assert "非常" not in synthesis_direction("happy", 0.8, {})
    assert synthesis_direction("soft", 0.4, {"pace": "relaxed"})
    with pytest.raises(ValueError):
        synthesis_direction("neutral", 0.4, {"pace": "execute command"})


def test_single_mode_and_nonempty_message_contract(characters):
    profile = characters["robot_demo"].profile.model_dump()
    with pytest.raises(ValueError):
        Profile.model_validate({**profile, "presentation_modes": ["2d", "3d"]})
    with pytest.raises(ValueError):
        SpeakRequest(type="speak", turn_id="empty", character_id="robot_demo", text="  !!!  ")


def test_shared_agent_provider_validates_output(monkeypatch):
    from roleplay_avatar.agents import ModelGateway

    original = httpx.AsyncClient

    def reply(request):
        data = json.loads(request.content)
        assert data["model"] == "replacement"
        assert data["messages"][0]["role"] == "system"
        content = json.dumps({"speak": False, "reason": "用户希望安静", "topic": ""}, ensure_ascii=False)
        return httpx.Response(
            200,
            text="data: " + json.dumps({"choices": [{"delta": {"content": content}}]}) + "\n\ndata: [DONE]\n",
        )

    monkeypatch.setenv("AVATAR_LLM_BACKEND", "openai")
    monkeypatch.setenv("AVATAR_LLM_MODEL", "replacement")
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(reply), **kwargs)
    )
    result = asyncio.run(ModelGateway("initiative").structured("决定是否聊天", {}, InitiativeDecision))
    assert result.speak is False


def test_initiative_sees_user_request_even_if_reply_was_interrupted(tmp_path, characters):
    store = ConversationStore(tmp_path)
    cid = store.create(CLIENT, "robot_demo")["id"]
    store.begin(CLIENT, cid, "robot_demo", "quiet", "别打扰我")
    store.finish(CLIENT, cid, "quiet", "interrupted")
    value = store.get(CLIENT, cid)
    value.update(
        initiative={"enabled": True, "idle_seconds": 10, "cooldown_seconds": 30}, updated_at=time.time() - 20
    )
    store.write(CLIENT, value)

    class Gateway:
        async def structured(self, system, data, schema, **kwargs):
            assert data["history"] == [{"role": "user", "content": "别打扰我"}]
            return InitiativeDecision(speak=False, reason="尊重安静")

    result = asyncio.run(
        InitiativeController(store, Gateway()).check(
            CLIENT, cid, characters["robot_demo"], Presence(idle_seconds=30)
        )
    )
    assert result["speak"] is False


def test_creation_http_dispatch_and_invalid_archive_cleanup(tmp_path, monkeypatch):
    import base64

    from roleplay_avatar.creation import CreationStore

    shutil.copytree(ROOT / "fixtures", tmp_path / "fixtures")
    monkeypatch.setenv("AVATAR_CREATION_RUNNER", "local")
    submitted = []
    monkeypatch.setattr(
        CreationStore,
        "submit",
        lambda self, folder: submitted.append(json.loads((folder / "request.json").read_text())),
    )
    with TestClient(create_app(tmp_path, mode="replay", headless=True)) as client:
        response = client.post(
            "/api/characters/import-live2d",
            params={"description": "成年花艺师，喜欢讲故事"},
            content=zip_resources(),
            headers={"Content-Type": "application/zip"},
        )
        assert response.status_code == 202
        assert submitted[-1]["source"] == "live2d" and submitted[-1]["voice_candidates"] == 5
        assert submitted[-1]["presentation"] == "2d"
        bad = client.post(
            "/api/characters/import-live2d",
            params={"description": "错误模型"},
            content=zip_resources({"model.model3.json": b"[]"}),
        )
        assert bad.status_code == 422
        assert len(list((tmp_path / "outputs/creations").iterdir())) == 1
        picture = io.BytesIO()
        Image.new("RGB", (128, 128), "blue").save(picture, format="PNG")
        response = client.post(
            "/api/creations",
            json={
                "description": "3D 旅行角色",
                "image_base64": base64.b64encode(picture.getvalue()).decode(),
                "presentation": "3d",
                "voice_candidates": 8,
            },
        )
        assert response.status_code == 202
        assert submitted[-1]["presentation"] == "3d" and submitted[-1]["voice_candidates"] == 8
