import json

from roleplay_avatar.model_metadata import model_metadata, source_record


def test_custom_checkpoint_is_not_attributed_to_default_model(tmp_path, monkeypatch):
    path = tmp_path / "my-image-model"
    path.mkdir()
    monkeypatch.setenv("AVATAR_IMAGE_MODEL_PATH", str(path))
    monkeypatch.delenv("AVATAR_MODELS_CONFIG", raising=False)
    metadata = model_metadata("image")
    assert metadata == {"model": "my-image-model", "revision": "", "license": "unspecified"}
    assert source_record("image", metadata) == {
        "component": "image", "source": "my-image-model", "license": "unspecified",
    }


def test_snapshot_receipt_and_stage_revision_survive_repackaging(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint"
    path.mkdir()
    (path / ".avatar-download.json").write_text(json.dumps({
        "repo": "Qwen/Qwen3-VL-32B-Instruct", "revision": "actual-snapshot",
    }))
    monkeypatch.setenv("AVATAR_VISION_MODEL_PATH", str(path))
    monkeypatch.delenv("AVATAR_MODELS_CONFIG", raising=False)
    metadata = model_metadata("vision")
    assert metadata["model"] == "Qwen/Qwen3-VL-32B-Instruct"
    assert metadata["revision"] == "actual-snapshot"
    assert source_record("persona", metadata)["revision"] == "actual-snapshot"
    metadata["revision"] = ""
    assert "revision" not in source_record("persona", metadata)
