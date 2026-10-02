import asyncio

import pytest

from roleplay_avatar.adapters import ToneReplayTTS
from roleplay_avatar.contracts import Segment, SpeakRequest
from roleplay_avatar.conversations import ConversationStore
from roleplay_avatar.session import Session

CLIENT = "a" * 32
OTHER = "b" * 32


def test_storage_identity_restart_and_partial_context(tmp_path):
    store = ConversationStore(tmp_path)
    a = store.create(CLIENT, "a")["id"]
    b = store.create(CLIENT, "b")["id"]
    assert store.create(CLIENT, "a")["id"] == a
    with pytest.raises(ValueError):
        store.get(OTHER, a)
    with pytest.raises(ValueError, match="different character"):
        store.get(CLIENT, a, "b")
    assert store.begin(CLIENT, a, "a", "one", "苹果暗号") == []
    with pytest.raises(ValueError, match="active response"):
        store.begin(CLIENT, a, "a", "two", "重复")
    store.append(CLIENT, a, "one", {"text": "记住了", "actions": []})
    store.finish(CLIENT, a, "one", "complete")
    a2 = store.create(CLIENT, "a")["id"]
    assert a2 != a
    with pytest.raises(ValueError, match="unique"):
        store.begin(CLIENT, a, "a", "one", "重复旧编号")
    assert store.begin(CLIENT, a, "a", "two", "未完成的问题")[0]["content"] == "苹果暗号"
    store.append(CLIENT, a, "two", {"text": "半句", "actions": []})
    restarted = ConversationStore(tmp_path)
    record = restarted.get(CLIENT, a)
    assert record["messages"][-1]["status"] == "interrupted"
    assert len(restarted.history(record)) == 2
    assert restarted.history(restarted.get(CLIENT, b)) == []
    assert restarted.history(restarted.get(CLIENT, a2)) == []
    with pytest.raises(ValueError):
        restarted.path(CLIENT, "../escape")


def test_session_context_switch_reconnect_and_immediate_cancel(tmp_path, characters):
    async def run():
        store = ConversationStore(tmp_path)
        first = store.create(CLIENT, "robot_demo")["id"]
        other = store.create(CLIENT, "dragon_demo")["id"]
        histories = []

        class LLM:
            async def stream(self, turn_id, text, character, history=None):
                histories.append((character.profile.character_id, list(history)))
                yield Segment(turn_id=turn_id, segment_id=0, sequence=0, text="答复", actions=[])

        async def send(event):
            pass

        def session():
            return Session(
                send,
                characters,
                ToneReplayTTS(duration_samples=24, paced=False),
                LLM(),
                conversations=store,
                client_id=CLIENT,
            )

        def request(turn, cid, char="robot_demo"):
            return SpeakRequest(
                type="speak", turn_id=turn, character_id=char, conversation_id=cid, text="独立记忆"
            )

        s = session()
        await s.start(request("one", first))
        await s.task
        second = store.create(CLIENT, "robot_demo")["id"]
        await s.start(request("two", second))
        await s.task
        await s.start(request("three", other, "dragon_demo"))
        await s.task
        # New socket retains only the chosen thread's completed pairs.
        s = session()
        await s.start(request("four", first))
        await s.task
        assert [len(history) for _, history in histories] == [0, 0, 0, 2]
        with pytest.raises(ValueError, match="different character"):
            await s.start(request("bad", first, "dragon_demo"))
        await s.start(request("cancel", second))
        await s.cancel()  # Task has not entered its coroutine yet.
        assert store.get(CLIENT, second)["messages"][-1]["status"] == "interrupted"
        assert not store.active

    asyncio.run(run())


def test_http_cookie_and_websocket_character_boundary(tmp_path):
    import shutil

    from conftest import ROOT
    from fastapi.testclient import TestClient

    from roleplay_avatar.app import create_app

    shutil.copytree(ROOT / "fixtures", tmp_path / "fixtures")
    (tmp_path / "web").mkdir()
    app = create_app(tmp_path, mode="replay")
    with TestClient(app) as client:
        assert client.get("/api/conversations?character_id=robot_demo").status_code == 403
        initialized = client.post("/api/conversations/client")
        assert "HttpOnly" in initialized.headers["set-cookie"]
        a = client.post("/api/conversations", json={"character_id": "robot_demo"}).json()["id"]
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "speak",
                    "turn_id": "bad",
                    "character_id": "dragon_demo",
                    "conversation_id": a,
                    "text": "错误角色",
                }
            )
            assert ws.receive_json()["type"] == "request_error"
            ws.send_json(
                {
                    "type": "speak",
                    "turn_id": "correct",
                    "character_id": "robot_demo",
                    "conversation_id": a,
                    "text": "你好",
                }
            )
            event = ws.receive_json()
            assert event["type"] == "turn_start" and event["conversation_id"] == a
            while ws.receive_json()["type"] != "audio":
                pass
            ws.send_json({"type": "cancel", "turn_id": "correct"})
            while ws.receive_json()["type"] != "cancelled":
                pass
        messages = client.get("/api/conversations/" + a).json()["messages"]
        assert len(messages) == 2 and messages[-1]["status"] == "interrupted"
        assert client.get("/api/conversations?character_id=dragon_demo").json() == []
    with TestClient(app) as stranger:
        stranger.post("/api/conversations/client")
        assert stranger.get("/api/conversations/" + a).status_code == 404
