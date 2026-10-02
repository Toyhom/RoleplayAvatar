from conftest import ROOT
from fastapi.testclient import TestClient

from roleplay_avatar.app import create_app


def test_http_and_websocket_cancel():
    with TestClient(create_app(ROOT, mode="replay")) as client:
        assert client.get("/healthz").json()["mode"] == "diagnostic_tone"
        assert len(client.get("/api/characters").json()) == 3
        assert client.get("/api/characters/unknown").status_code == 404
        assert "镜界" in client.get("/").text
        assert client.get("/static/app.js").status_code == 200
        with client.websocket_connect("/ws") as ws:
            ws.send_text("invalid json")
            assert ws.receive_json()["type"] == "request_error"
            ws.send_json({"type": "speak", "turn_id": "web_1", "character_id": "robot_demo", "text": "你好"})
            assert ws.receive_json()["data"]["active_streams"] == ["audio", "motion"]
            while ws.receive_json()["type"] != "audio":
                pass
            ws.send_json({"type": "cancel", "turn_id": "web_1"})
            while ws.receive_json()["type"] != "cancelled":
                pass
            ws.send_json(
                {"type": "speak", "turn_id": "web_2", "character_id": "dragon_demo", "text": "下一轮"}
            )
            event = ws.receive_json()
            assert event["type"] == "turn_start" and event["turn_id"] == "web_2"
