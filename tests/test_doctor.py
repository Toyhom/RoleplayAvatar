import json

from roleplay_avatar.doctor import checkpoint_files


def test_incomplete_diffusers_snapshot_reports_shards_and_vae(tmp_path):
    (tmp_path / "model_index.json").write_text(json.dumps({
        "transformer": ["diffusers", "QwenImageTransformer2DModel"],
        "vae": ["diffusers", "AutoencoderKLQwenImage"],
        "scheduler": ["diffusers", "FlowMatchEulerDiscreteScheduler"],
    }))
    for name in ("transformer", "vae", "scheduler"):
        (tmp_path / name).mkdir()
    (tmp_path / "transformer/model.index.json").write_text(json.dumps({
        "weight_map": {"layer1": "model-1.safetensors", "layer2": "model-2.safetensors"},
    }))
    (tmp_path / "transformer/model-1.safetensors").write_bytes(b"weights")
    problems = checkpoint_files(tmp_path)
    assert any("model-2.safetensors" in p for p in problems)
    assert any("vae" in p for p in problems)
    assert not any("scheduler" in p for p in problems)
    (tmp_path / "transformer/model-2.safetensors").write_bytes(b"weights")
    (tmp_path / "vae/diffusion_pytorch_model.safetensors").write_bytes(b"weights")
    assert checkpoint_files(tmp_path) == []


def test_download_receipt_detects_truncated_file(tmp_path):
    (tmp_path / ".avatar-download.json").write_text(json.dumps({
        "files": [{"file": "model.safetensors", "size": 8}],
    }))
    (tmp_path / "model.safetensors").write_bytes(b"short")
    assert checkpoint_files(tmp_path) == ["Incomplete downloaded file: model.safetensors"]


def test_standalone_resource_and_malformed_metadata(tmp_path):
    file = tmp_path / "landmarks.task"
    file.write_bytes(b"task")
    assert checkpoint_files(file) == []
    (tmp_path / "model.index.json").write_text("{unfinished")
    assert checkpoint_files(tmp_path) == ["Cannot inspect checkpoint metadata: JSONDecodeError"]
