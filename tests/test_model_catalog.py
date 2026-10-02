from roleplay_avatar.model_catalog import PRESETS, catalog, download_plan, preset_config, recommend


def test_presets_resolve_pinned_snapshots_without_downloading(tmp_path):
    models = catalog()
    for name in PRESETS:
        plan = download_plan(name, tmp_path, "https://hf-mirror.com", creation=True)
        assert plan and all(len(e["revision"]) == 40 for e in plan)
        assert all(e["path"].startswith(str(tmp_path)) for e in plan)
        assert all(e["endpoint"] == "https://hf-mirror.com" for e in plan)
    assert models["coser-70b"]["output_mode"] == "actor_director"
    assert models["qwen-voice-design"]["repo"].endswith("VoiceDesign")


def test_hardware_recommendation_accounts_for_concurrent_services():
    assert recommend(8)["preset"] == "api"
    assert recommend(24)["preset"] == "compact"
    assert recommend(48)["preset"] == "balanced"
    assert recommend(80, 2)["preset"] == "quality"
    assert recommend(80, 3)["preset"] == "showcase"


def test_showcase_keeps_general_agents_on_controller(tmp_path):
    config = preset_config("showcase", tmp_path)
    assert config["agents"]["roleplay"]["url"] != config["agents"]["default"]["url"]
    assert config["models"]["controller"]["repo"] == "Qwen/Qwen3-8B"


def test_mirror_download_validates_bytes_and_requires_selected_files(tmp_path, monkeypatch):
    import hashlib
    import sys
    from types import SimpleNamespace

    import pytest

    from roleplay_avatar.model_catalog import download

    raw = b"real fixture weights"
    sha = hashlib.sha256(raw).hexdigest()
    revision = "f" * 40
    calls = []
    files = [SimpleNamespace(rfilename="model.safetensors", size=len(raw), lfs=SimpleNamespace(sha256=sha))]

    class API:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def model_info(self, *args, **kwargs):
            return SimpleNamespace(sha=revision, siblings=files)

    def snapshot(*args, **kwargs):
        assert kwargs["endpoint"] == "https://hf-mirror.com" and kwargs["token"] is False
        (tmp_path / "model.safetensors").write_bytes(raw)

    monkeypatch.setenv("HF_TOKEN", "a-personal-token")
    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(HfApi=API, snapshot_download=snapshot)
    )
    entry = {
        "endpoint": "https://hf-mirror.com",
        "repo": "test/checkpoint",
        "revision": revision,
        "path": str(tmp_path),
        "adapter": "transformers-causal",
    }
    download(entry)
    assert calls[0]["token"] is False
    assert (tmp_path / ".avatar-download.json").exists()
    (tmp_path / "model.safetensors").unlink()
    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(HfApi=API, snapshot_download=lambda *a, **k: None)
    )
    with pytest.raises(ValueError, match="Missing snapshot file"):
        download(entry)
