"""Portable launch plans for local OpenAI-compatible inference engines."""

import hashlib
import json
import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import configuration, configured_path, model_path


class EngineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["vllm", "sglang", "llama.cpp"] = "vllm"
    python: str = sys.executable
    executable: str = "llama-server"
    served_model: str = "roleplay"
    host: str = "127.0.0.1"
    port: int = Field(default=18110, ge=1, le=65535)
    context: int = Field(default=8192, ge=256)
    dtype: Literal["auto", "bfloat16", "float16", "float32"] = "auto"
    tensor_parallel: int = Field(default=1, ge=1)
    gpu_memory_utilization: float = Field(default=0.6, gt=0, lt=1)
    max_sequences: int = Field(default=4, ge=1)
    max_batch_tokens: int = Field(default=2048, ge=256)
    prefix_caching: bool = True
    chunked_prefill: bool = True
    kv_cache_dtype: str = "auto"
    quantization: str | None = None
    cpu_offload_gb: float = Field(default=0, ge=0)
    enforce_eager: bool = False
    chat_template: str | None = None
    template_kwargs: dict = Field(default_factory=dict)
    gpu_layers: int = Field(default=-1, ge=-1)
    extra_args: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def compatible_options(self):
        if self.engine == "llama.cpp":
            supplied = self.model_fields_set
            unsupported = supplied & {
                "dtype", "tensor_parallel", "gpu_memory_utilization", "quantization", "cpu_offload_gb",
                "enforce_eager", "chunked_prefill", "prefix_caching",
            }
            if unsupported:
                raise ValueError("llama.cpp uses GGUF weights and GPU layers; remove " + ", ".join(sorted(unsupported)))
            if self.kv_cache_dtype not in {"auto", "f16", "q8_0", "q4_0"}:
                raise ValueError("llama.cpp KV cache dtype: auto, f16, q8_0 or q4_0")
        elif self.gpu_layers != -1:
            raise ValueError("gpu_layers applies to llama.cpp")
        if self.engine == "vllm" and not self.chunked_prefill and self.max_batch_tokens < self.context:
            raise ValueError("Without chunked prefill, max_batch_tokens must cover context")
        return self


def engine_config(role="roleplay", *, overrides=None):
    entries = configuration().get("inference", {})
    if role not in entries:
        raise ValueError(f"Configure inference.{role}; see guides/performance.md")
    return EngineConfig.model_validate({**entries[role], **(overrides or {})})


def launch_plan(role="roleplay", *, config=None, model=None, check=False):
    """Build argv without a shell, CUDA discovery, imports of Torch, or environment changes."""
    cfg = config or engine_config(role)
    path = configured_path(model) if model else model_path(role, check=check)
    if check and not path.exists():
        raise FileNotFoundError(f"Model is missing: {path}")
    if cfg.engine == "llama.cpp" and path.suffix.lower() != ".gguf":
        raise ValueError("llama.cpp requires models.<role>.path to point to a GGUF file")
    if cfg.engine != "llama.cpp" and path.suffix.lower() == ".gguf":
        raise ValueError("Select llama.cpp for a GGUF checkpoint")
    common = ["--host", cfg.host, "--port", str(cfg.port)]
    if cfg.engine == "vllm":
        command = [os.path.expanduser(os.path.expandvars(cfg.python)), "-m", "vllm.entrypoints.openai.api_server",
                   "--model", str(path), "--served-model-name", cfg.served_model, *common,
                   "--dtype", cfg.dtype, "--tensor-parallel-size", str(cfg.tensor_parallel),
                   "--max-model-len", str(cfg.context),
                   "--gpu-memory-utilization", str(cfg.gpu_memory_utilization),
                   "--max-num-seqs", str(cfg.max_sequences),
                   "--max-num-batched-tokens", str(cfg.max_batch_tokens),
                   "--kv-cache-dtype", cfg.kv_cache_dtype,
                   "--enable-prefix-caching" if cfg.prefix_caching else "--no-enable-prefix-caching",
                   "--enable-chunked-prefill" if cfg.chunked_prefill else "--no-enable-chunked-prefill"]
        if cfg.enforce_eager:
            command.append("--enforce-eager")
    elif cfg.engine == "sglang":
        command = [os.path.expanduser(os.path.expandvars(cfg.python)), "-m", "sglang.launch_server",
                   "--model-path", str(path), "--served-model-name", cfg.served_model, *common,
                   "--dtype", cfg.dtype, "--tp-size", str(cfg.tensor_parallel),
                   "--context-length", str(cfg.context),
                   "--mem-fraction-static", str(cfg.gpu_memory_utilization),
                   "--max-running-requests", str(cfg.max_sequences),
                   "--chunked-prefill-size", str(cfg.max_batch_tokens if cfg.chunked_prefill else -1),
                   "--kv-cache-dtype", cfg.kv_cache_dtype]
        if not cfg.prefix_caching:
            command.append("--disable-radix-cache")
        if cfg.enforce_eager:
            command.append("--disable-cuda-graph")
    else:
        command = [os.path.expanduser(os.path.expandvars(cfg.executable)), "--model", str(path), "--alias", cfg.served_model,
                   *common, "--ctx-size", str(cfg.context * cfg.max_sequences),
                   "--parallel", str(cfg.max_sequences), "--batch-size", str(cfg.max_batch_tokens),
                   "--n-gpu-layers", str(cfg.gpu_layers), "--cont-batching", "--jinja",
                   "--flash-attn", "on", "--cache-type-k", "f16" if cfg.kv_cache_dtype == "auto" else cfg.kv_cache_dtype,
                   "--cache-type-v", "f16" if cfg.kv_cache_dtype == "auto" else cfg.kv_cache_dtype]
    if cfg.engine != "llama.cpp":
        if cfg.quantization and cfg.quantization != "none":
            command += ["--quantization", cfg.quantization]
        if cfg.cpu_offload_gb:
            command += ["--cpu-offload-gb", str(cfg.cpu_offload_gb)]
    if cfg.chat_template:
        template = configured_path(cfg.chat_template)
        if check and not template.is_file():
            raise FileNotFoundError(f"Chat template is missing: {template}")
        command += ["--chat-template-file" if cfg.engine == "llama.cpp" else "--chat-template", str(template)]
    command += cfg.extra_args
    if check:
        if not shutil.which(command[0]):
            raise FileNotFoundError(f"Inference executable is missing: {command[0]}")
        visible = os.environ.get("CUDA_VISIBLE_DEVICES")
        if visible is not None and cfg.engine != "llama.cpp":
            count = len([v for v in visible.split(",") if v.strip() and v.strip() != "-1"])
            if count < cfg.tensor_parallel:
                raise ValueError(f"tensor_parallel={cfg.tensor_parallel} needs more than {count} visible GPUs")
    host = "127.0.0.1" if cfg.host in {"0.0.0.0", "::"} else cfg.host
    if ":" in host:
        host = "[" + host.strip("[]") + "]"
    base = f"http://{host}:{cfg.port}"
    provider = {"provider": "openai-compatible", "url": base + "/v1",
                "model": cfg.served_model, "require_key": False}
    if cfg.template_kwargs:
        provider["extra_body"] = {"chat_template_kwargs": cfg.template_kwargs}
    return {"engine": cfg.engine, "role": role, "command": command, "shell_display": shlex.join(command),
            "health_url": base + ("/health" if cfg.engine != "sglang" else "/health_generate"),
            "agent": provider, "context_per_request": cfg.context}


def start(role="roleplay", *, config=None, model=None):
    command = launch_plan(role, config=config, model=model, check=True)["command"]
    env = dict(os.environ)
    # Absolute Python paths select a virtualenv without shell activation. Native
    # extensions also need that environment's executables, including ninja.
    executable = shutil.which(command[0])
    directory = str(Path(executable).absolute().parent)
    env["PATH"] = directory + os.pathsep + env.get("PATH", os.defpath)
    os.execvpe(command[0], command, env)


def fingerprint(role="roleplay", *, config=None, model=None):
    plan = launch_plan(role, config=config, model=model)
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
