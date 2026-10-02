import asyncio
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from roleplay_avatar.inference import EngineConfig, engine_config, launch_plan, start
from roleplay_avatar.model_catalog import preset_config
from roleplay_avatar.models import agent_config
from roleplay_avatar.voice_cache import VoicePromptCache


@pytest.mark.parametrize("engine", ["vllm", "sglang"])
def test_accelerated_preset_routes_each_agent_to_its_engine(engine, tmp_path, monkeypatch):
    config = preset_config("showcase", tmp_path, engine=engine, inference_python=sys.executable)
    path = tmp_path / "models.json"
    path.write_text(json.dumps(config))
    monkeypatch.setenv("AVATAR_MODELS_CONFIG", str(path))
    for agent, role in [("roleplay", "roleplay"), ("initiative", "controller"), ("voice_direction", "controller")]:
        route = agent_config(agent)
        plan = launch_plan(role)
        assert route["url"] == plan["agent"]["url"]
        assert route["model"] == plan["agent"]["model"]
        assert route["backend"] == "openai"
    assert agent_config("roleplay")["output_mode"] == "actor_director"
    assert agent_config("initiative")["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert engine_config("roleplay").tensor_parallel == 2


def test_launch_preserves_allocation_and_passes_paths_without_shell(tmp_path, monkeypatch):
    import roleplay_avatar.inference as module

    model = tmp_path / "model $(do-not-execute)"
    model.mkdir()
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-one,GPU-two")
    cfg = EngineConfig(python=sys.executable, tensor_parallel=2, kv_cache_dtype="fp8", quantization="awq",
                       prefix_caching=False, cpu_offload_gb=4)
    called = []
    monkeypatch.setattr(module.os, "execvpe", lambda *args: called.append(args))
    start(config=cfg, model=str(model))
    _, argv, env = called[0]
    assert env["CUDA_VISIBLE_DEVICES"] == "GPU-one,GPU-two"
    assert str(model) in argv
    assert argv[argv.index("--quantization") + 1] == "awq"
    assert "--no-enable-prefix-caching" in argv
    assert argv[argv.index("--kv-cache-dtype") + 1] == "fp8"
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-one")
    with pytest.raises(ValueError, match="visible GPUs"):
        start(config=cfg, model=str(model))


def test_queued_launch_fingerprint_tracks_engine_and_template_changes(tmp_path):
    from roleplay_avatar.inference import fingerprint

    path = str(tmp_path / "model")
    base = fingerprint(config=EngineConfig(context=4096), model=path)
    assert base != fingerprint(config=EngineConfig(context=8192), model=path)
    assert base != fingerprint(config=EngineConfig(context=4096, template_kwargs={"enable_thinking": False}), model=path)


def test_llama_context_is_per_slot_and_unsupported_controls_fail(tmp_path):
    cfg = EngineConfig(engine="llama.cpp", max_sequences=2, context=4096, kv_cache_dtype="q8_0")
    command = launch_plan(config=cfg, model=str(tmp_path / "model.gguf"))["command"]
    assert command[command.index("--ctx-size") + 1] == "8192"
    assert command[command.index("--cache-type-k") + 1] == "q8_0"
    with pytest.raises(ValueError, match="GGUF"):
        launch_plan(config=cfg, model=str(tmp_path / "transformers-model"))
    with pytest.raises(ValueError, match="remove"):
        EngineConfig(engine="llama.cpp", gpu_memory_utilization=0.5)


@pytest.mark.parametrize("options", [
    {"gpu_memory_utilization": 1}, {"tensor_parallel": 0}, {"max_sequences": 0},
    {"chunked_prefill": False, "context": 8192, "max_batch_tokens": 1024}, {"typo_memory_fraction": 0.5},
])
def test_invalid_engine_configuration_fails_before_loading_weights(options):
    with pytest.raises(ValueError):
        EngineConfig(**options)


def test_voice_conditioning_cache_reuses_invalidates_and_evicts(tmp_path):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"first reference")
    cache = VoicePromptCache(1)
    count = []

    def build():
        value = object()
        count.append(value)
        return value

    first = cache.get(audio, "hello", build)
    assert cache.get(audio, "hello", build) is first
    assert cache.get(audio, "edited transcript", build) is not first
    audio.write_bytes(b"replacement reference")
    assert cache.get(audio, "edited transcript", build) is count[-1]
    assert len(count) == 3 and len(cache.entries) == 1
    disabled = VoicePromptCache(0)
    assert disabled.get(audio, "hello", build) is not disabled.get(audio, "hello", build)


def test_faster_whisper_wire_contract_and_silence():
    pytest.importorskip("numpy")
    from services.faster_whisper_service import create_app

    calls = []

    def transcribe(samples, **kwargs):
        calls.append(kwargs)
        return iter([SimpleNamespace(text=" Hello"), SimpleNamespace(text=" world")]), SimpleNamespace(language="en")

    with TestClient(create_app(SimpleNamespace(transcribe=transcribe), model_path="model")) as client:
        assert client.post("/transcribe", json={"pcm_base64": "invalid!"}).status_code == 422
        assert client.post("/transcribe", json={"pcm_base64": "YQ=="}).status_code == 422
        silence = base64.b64encode(b"\x00\x00" * 3200).decode()
        assert client.post("/transcribe", json={"pcm_base64": silence}).json()["reason"] == "silence"
        assert not calls
        signal = base64.b64encode(b"\x00\x10" * 3200).decode()
        result = client.post("/transcribe", json={"pcm_base64": signal})
        assert result.json()["text"] == "Hello world"
        assert result.json()["language"] == "en"
        assert calls[0]["language"] is None
        assert client.get("/healthz").json()["completed_requests"] == 1


def test_benchmark_uses_server_token_usage_and_rejects_empty_stream():
    from scripts.benchmark_inference import measure

    async def run():
        events = 'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        events += 'data: {"choices":[],"usage":{"completion_tokens":1}}\n\ndata: [DONE]\n\n'
        transport = httpx.MockTransport(lambda _: httpx.Response(200, text=events))
        async with httpx.AsyncClient(transport=transport) as client:
            result = await measure(client, "http://test/v1/chat/completions", {}, "openai")
            assert result["characters"] == 5 and result["usage"]["completion_tokens"] == 1
            assert 0 <= result["ttft_s"] <= result["elapsed_s"]
        transport = httpx.MockTransport(lambda _: httpx.Response(200, text='data: [DONE]\n\n'))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(RuntimeError, match="no visible text"):
                await measure(client, "http://test/v1/chat/completions", {}, "openai")

    asyncio.run(run())


def test_image_memory_controls_support_different_vae_capabilities():
    from roleplay_avatar.image_runtime import configure_pipeline

    calls = []
    pipe = SimpleNamespace(vae=SimpleNamespace(enable_tiling=lambda: calls.append("tile")),
                           enable_model_cpu_offload=lambda: calls.append("model"),
                           enable_sequential_cpu_offload=lambda: calls.append("sequential"),
                           to=lambda device: calls.append(device))
    runtime = configure_pipeline(pipe, {})
    assert runtime["vae_tiling"] and not runtime["vae_slicing"]
    assert calls == ["tile", "model"]
    configure_pipeline(pipe, {"offload": "sequential", "vae_tiling": False})
    assert calls[-1] == "sequential"
    with pytest.raises(ValueError, match="slicing"):
        configure_pipeline(pipe, {"vae_slicing": True})
    with pytest.raises(ValueError, match="offload=none"):
        configure_pipeline(pipe, {"compile": True})


def test_health_probe_understands_empty_vllm_health_and_loading():
    import io
    import urllib.error

    from roleplay_avatar.service_health import probe

    urls = []

    def open_ready(url, **kwargs):
        urls.append(url)
        if url.endswith("healthz"):
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        response = io.BytesIO(b"")
        response.status = 200
        return response

    assert probe(18110, opener=SimpleNamespace(open=open_ready)) == {"status": "ready"}
    assert [u.rsplit("/", 1)[1] for u in urls] == ["healthz", "health"]

    def loading(url, **kwargs):
        raise urllib.error.HTTPError(url, 503, "loading", {}, None)

    assert probe(18110, opener=SimpleNamespace(open=loading)) == {"status": "unavailable"}


def test_service_group_preserves_scheduler_allocation(tmp_path):
    root = Path(__file__).resolve().parents[1]
    path = tmp_path / "services.json"
    path.write_text(json.dumps({"services": {"test": {
        "python": sys.executable, "script": "unused.py", "model": str(tmp_path), "port": 18999,
        "env": {"CUDA_VISIBLE_DEVICES": "different-device"},
    }}}))
    result = subprocess.run([sys.executable, str(root / "services/service_group.py"), "--config", str(path)],
                            cwd=root, env={**os.environ, "CUDA_VISIBLE_DEVICES": "allocated-device"},
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode != 0
    assert "must preserve the GPU allocation" in result.stderr


def test_vllm_uuid_plugin_maps_only_allocated_identifiers(monkeypatch):
    from roleplay_avatar.vllm_devices import register

    class Platform:
        device_control_env_var = "CUDA_VISIBLE_DEVICES"

        @classmethod
        def device_id_to_physical_device_id(cls, ordinal):
            return int(os.environ[cls.device_control_env_var].split(",")[ordinal])

    shutdowns = []
    nvml = SimpleNamespace(nvmlInit=lambda: None, nvmlShutdown=lambda: shutdowns.append(True),
                           nvmlDeviceGetHandleByUUID=lambda uid: {"GPU-a": 5, "GPU-b": 2}[uid],
                           nvmlDeviceGetIndex=lambda handle: handle)
    monkeypatch.setitem(sys.modules, "vllm", SimpleNamespace(__version__="0.21.0"))
    monkeypatch.setitem(sys.modules, "vllm.platforms.interface", SimpleNamespace(Platform=Platform))
    monkeypatch.setitem(sys.modules, "pynvml", nvml)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-b,GPU-a")
    register()
    register()
    assert Platform.device_id_to_physical_device_id(0) == 2
    assert Platform.device_id_to_physical_device_id(1) == 5
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "GPU-b,GPU-a"
    assert len(shutdowns) == 2
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "3,1")
    assert Platform.device_id_to_physical_device_id(1) == 1
