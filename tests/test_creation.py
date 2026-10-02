import base64
import io
import json
import shutil

import pytest
from conftest import ROOT
from fastapi.testclient import TestClient
from PIL import Image

from roleplay_avatar.app import create_app
from roleplay_avatar.creation import CreationRequest, CreationStore, read_json
from roleplay_avatar.live import PerformanceParser


def picture(size=(128, 128)):
    stream = io.BytesIO()
    Image.new("RGB", size, (90, 160, 120)).save(stream, format="PNG")
    return base64.b64encode(stream.getvalue()).decode()


@pytest.mark.parametrize("locale", ["en", "zh-CN", "ja"])
def test_creation_preserves_input_and_submission_receipt(tmp_path, monkeypatch, locale):
    store = CreationStore(tmp_path, runner="gpuq")
    submitted = []
    monkeypatch.setattr(store, "submit", lambda folder: submitted.append(folder))
    result = store.create(CreationRequest(description="温柔的林间向导", image_base64=picture(), locale=locale))
    assert result["state"] == "queued"
    assert result["description"] == "温柔的林间向导"
    folder = submitted[0]
    assert read_json(folder / "request.json")["input_sha256"]
    assert read_json(folder / "request.json")["presentation"] == "2d"
    assert read_json(folder / "request.json")["locale"] == locale
    assert Image.open(folder / "input.png").size == (128, 128)
    assert store.list()[0]["id"] == result["id"]
    with pytest.raises(ValueError):
        store.folder("../../etc")


@pytest.mark.parametrize("data", [base64.b64encode(b"this is not an image" * 4).decode(), picture((32, 32))])
def test_invalid_image_does_not_create_or_submit_job(tmp_path, monkeypatch, data):
    store = CreationStore(tmp_path, runner="gpuq")
    monkeypatch.setattr(store, "submit", lambda _: pytest.fail("Invalid image was submitted"))
    with pytest.raises(ValueError):
        store.create(CreationRequest(description="角色", image_base64=data))
    assert not store.list()


def test_partial_performance_json_never_leaks_control_into_text():
    parser = PerformanceParser()
    text = json.dumps(
        {
            "text": "太好了！一起去看看吧。",
            "emotion": "happy",
            "intensity": 0.7,
            "action_intent": "acknowledge",
        },
        ensure_ascii=False,
    )
    results = []
    for character in text:
        results.extend(parser.feed(character))
    assert results == [
        {
            "text": "太好了！一起去看看吧。",
            "emotion": "happy",
            "intensity": 0.7,
            "action_intent": "acknowledge",
        }
    ]


def test_untrusted_performance_is_bounded():
    parser = PerformanceParser()
    items = parser.feed('{"text":"你好。","emotion":"execute","action_intent":"../../run","intensity":999}')
    assert items[0]["emotion"] == "neutral"
    assert items[0]["action_intent"] == "speak"
    assert items[0]["intensity"] == 0.4
    with pytest.raises(ValueError):
        parser.feed("x" * 17000)


def test_studio_api_rejects_cross_origin_and_hides_worker_files(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "fixtures", tmp_path / "fixtures")
    (tmp_path / "web").mkdir()
    monkeypatch.setenv("AVATAR_CREATION_RUNNER", "gpuq")
    monkeypatch.setattr(CreationStore, "submit", lambda *_: None)
    with TestClient(create_app(tmp_path, mode="replay")) as client:
        payload = {"description": "勇敢的机械朋友", "image_base64": picture()}
        assert (
            client.post(
                "/api/creations", json=payload, headers={"origin": "https://unrelated.example"}
            ).status_code
            == 403
        )
        response = client.post("/api/creations", json=payload)
        assert response.status_code == 202
        job = response.json()
        assert client.get(job["image_url"]).status_code == 200
        assert client.get(f"/api/creations/{job['id']}/files/request.json").status_code == 404
        assert client.get(f"/api/creations/{job['id']}").json()["state"] == "queued"
        assert client.get("/api/creations/bogus").status_code == 404


def test_hiding_old_live_assets_does_not_hide_replay_fixtures(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "fixtures", tmp_path / "fixtures")
    (tmp_path / "web").mkdir()
    monkeypatch.setenv("AVATAR_HIDE_LEGACY", "1")
    with TestClient(create_app(tmp_path, mode="replay")) as client:
        assert len(client.get("/api/characters").json()) == 3
