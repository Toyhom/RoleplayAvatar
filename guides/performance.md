# Local inference and performance

[English](performance.md) · [简体中文](zh-CN/performance.md) · [日本語](ja/performance.md)

Local model services have independent runtimes and memory budgets. Agents share an inference endpoint when they use the same checkpoint, so dialogue, initiative and character design can reuse one set of weights. Provider APIs continue to use the configuration in [Providers](providers.md).

## Choose a runtime

| Module | Runtime | Main controls |
| --- | --- | --- |
| Dialogue and control agents | vLLM | Continuous batching, prefix cache, chunked prefill, tensor parallelism, quantized weights and KV cache |
| Dialogue and supported vision models | SGLang | Continuous batching, RadixAttention prefix cache, tensor parallelism and quantization |
| GGUF dialogue models | llama.cpp `llama-server` | Quantized weights/KV cache, GPU layer offload, CPU/GPU execution and parallel slots |
| Transformers dialogue | Bundled `llm_service.py` | SDPA, BF16/FP16, bitsandbytes INT4/INT8 and device mapping |
| Whisper ASR | faster-whisper / CTranslate2 | FP16 or INT8 computation, beam size and CPU/GPU selection |
| Qwen3-TTS | Native Torch runtime | SDPA or FlashAttention 2, dtype and cached reference conditioning |
| CosyVoice3 | Native runtime / TensorRT | Streaming synthesis, FP16 and TensorRT flow engine |
| Image generation | Diffusers / Accelerate | Model or sequential CPU offload, VAE tiling/slicing and optional compilation |
| Audio-to-face | ONNX Runtime | Independent CUDA inference service |

Model architecture and quantization support depend on the selected runtime version and GPU. Use its supported-model list when selecting a checkpoint: [vLLM](https://docs.vllm.ai/en/latest/models/supported_models.html), [SGLang](https://docs.sglang.ai/supported_models/generative_models.html), [llama.cpp](https://github.com/ggml-org/llama.cpp). Vision models use the image-message path through `agents.vision` and `models.vision.adapter="api"`.

## Start with vLLM

Create a dedicated Python 3.11 environment and generate a configuration:

```bash
bash scripts/install_model_env.sh vllm /absolute/python3.11 /srv/envs/avatar-vllm
.venv/bin/avatar models configure compact --engine vllm \
  --inference-python /srv/envs/avatar-vllm/bin/python \
  --model-root /srv/models --output configs/models.local.json
export AVATAR_MODELS_CONFIG="$PWD/configs/models.local.json"
.venv/bin/avatar inference plan --role roleplay
```

Download the selected models using [the model catalog](models.md). `inference plan` prints the exact command and matching agent endpoint. Run this payload with your GPU runner:

```bash
.venv/bin/avatar inference start --role roleplay
```

On a shared GPUQ server, submit the command under your account using `gpuq submit --node auto --gpus N -- /absolute/path/to/.venv/bin/avatar inference start --role roleplay`. The process inherits the allocated CUDA devices. `tensor_parallel` must fit the allocation. Use an absolute interpreter path when submitting a queued job.

The installer pins vLLM in `requirements/vllm.txt` and records installed packages in the new environment. Inference environments have their own Torch dependencies. The CPU application remains in `.venv`. For SGLang, replace the installer kind and `--engine` with `sglang`.

The vLLM installer also registers the framework’s device plugin. With vLLM 0.21, it resolves allocated GPU UUIDs through NVML while preserving `CUDA_VISIBLE_DEVICES`.

## Configure memory and concurrency

Start from [inference.example.json](../configs/inference.example.json). Its `models` section selects checkpoints, `inference` selects local processes, and `agents` routes requests. Each named inference entry can serve several agents. `avatar doctor` validates the entries and local paths.

| Setting | Effect and starting point |
| --- | --- |
| `context` | Maximum prompt plus output tokens per request; start at 4096–8192. |
| `gpu_memory_utilization` | vLLM per-GPU memory budget; SGLang static-memory fraction. Leave capacity for speech, ASR and transient allocations. |
| `max_sequences` | Maximum active requests; start at 1–4 for an interactive installation. |
| `max_batch_tokens` | vLLM token batch budget / SGLang prefill chunk size. 2048 is a starting point for interleaving long prompts and active replies. |
| `prefix_caching` | Reuse repeated persona/prompt prefixes across requests. |
| `chunked_prefill` | Split prompt processing into smaller batches. |
| `tensor_parallel` | Split one model across the allocated GPUs. |
| `quantization` | Engine-specific weight format, such as `awq`, `gptq` or `fp8`; select a matching checkpoint and supported runtime. |
| `kv_cache_dtype` | Cache precision, separate from weight precision. `fp8` reduces cache size on supporting vLLM/SGLang installations. |
| `cpu_offload_gb` | Engine-managed weight offload; saves VRAM and adds host-to-device transfers. |
| `enforce_eager` | Disable CUDA graphs to reduce graph memory, with a throughput tradeoff. |
| `chat_template`, `template_kwargs` | Model-specific prompt template and generation-mode switches. |
| `extra_args` | Additional native command arguments as a JSON string array. |

GPU memory includes weights, KV cache, CUDA graphs, activations and other services. Approximate **weight-only** sizes in decimal GB are:

| Parameters | 16-bit | 8-bit | 4-bit |
| --- | ---: | ---: | ---: |
| 4B | 8 | 4 | 2 |
| 8B | 16 | 8 | 4 |
| 32B | 64 | 32 | 16 |
| 70B | 140 | 70 | 35 |

Quantization adds scales and metadata. KV cache grows with context and concurrent requests. A high preallocated cache can make a fast engine occupy more VRAM than a single-request Transformers service; lower its budget to share a GPU with speech. Run character creation in a separate allocation or at a different time.

## GGUF and smaller machines

Build or install [llama-server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server) with the backend for your device. Point `models.roleplay.path` to a GGUF file and use:

```json
{
  "engine": "llama.cpp", "executable": "/srv/llama.cpp/build/bin/llama-server",
  "served_model": "avatar-roleplay", "port": 18110,
  "context": 4096, "max_sequences": 1, "gpu_layers": -1,
  "kv_cache_dtype": "q8_0"
}
```

Put this entry under `inference.roleplay`; use the OpenAI-compatible agent settings from the example configuration. `gpu_layers=0` selects CPU execution. Smaller positive values partially offload layers. GGUF determines weight quantization. The launcher allocates `context × max_sequences` total context for llama.cpp parallel slots. Native llama.cpp flags go in `extra_args`.

## Accelerate speech and images

**ASR:** install the `faster-whisper` environment. Use a CTranslate2 Whisper checkpoint, or convert an existing Transformers checkpoint in an environment with CTranslate2, Transformers and Torch:

```bash
ct2-transformers-converter --model /srv/models/whisper \
  --output_dir /srv/models/whisper-ct2 --quantization float16 \
  --copy_files tokenizer.json preprocessor_config.json
/srv/envs/avatar-faster-whisper/bin/python services/faster_whisper_service.py \
  --model /srv/models/whisper-ct2 --compute-type int8_float16 --port 18140
```

The service warms up before becoming ready; `--no-warmup` skips this startup pass. It keeps the microphone `/transcribe` contract and automatic language detection. `--beam-size 1` favors latency; larger beams can improve recognition. CPU inference uses `--device cpu --compute-type int8`. [faster-whisper](https://github.com/SYSTRAN/faster-whisper) documents the CUDA/cuDNN requirements for CTranslate2.

**Qwen3-TTS:** `family_speech_service.py --backend qwen-base` caches up to eight reference voice prompts. Editing the audio or transcript invalidates its cache entry. `--voice-cache-size 0` disables caching. `/healthz` reports cache hits and misses. Select `--attention sdpa` or `--attention flash_attention_2` with a compatible FlashAttention installation; `--dtype` controls model precision. Audio is still generated per sentence, then streamed as contiguous 24 kHz PCM.

**CosyVoice3:** `speech_service.py --fp16` selects the native half-precision path; `--tensorrt` enables the upstream flow engine. Install the upstream-compatible TensorRT packages in its dedicated environment. Engine construction happens on the target GPU at startup; retain the resulting plan with that deployment. See [CosyVoice](https://github.com/FunAudioLLM/CosyVoice).

**Images:** set `models.image.offload` or `models.image_edit.offload` to `model` (default), `sequential` (lowest residency, more transfers), or `none` (resident on GPU). `vae_tiling` and `vae_slicing` are enabled by default when supported by the VAE. `compile=true` with `offload="none"` enables Torch compilation; it is most useful for repeatedly used shapes and adds cold-start time. The creation worker normally loads each stage in a separate process.

## Measure your deployment

Run the same prompt, model, context and output limit when comparing engines:

```bash
.venv/bin/python scripts/benchmark_inference.py \
  --url http://127.0.0.1:18110/v1 --model avatar-roleplay \
  --requests 8 --concurrency 4 --max-tokens 128 \
  --template-kwargs '{"enable_thinking":false}' \
  --output outputs/benchmarks/vllm-c4.json
```

Use `--backend local --url http://127.0.0.1:18110` for the bundled Transformers service. The benchmark records warm first-text latency, total latency, failures, output characters and server-reported token throughput. Change `--prompt` and concurrency to match your workload. Test cancellation and voice intelligibility alongside speed; quantization and dtype changes can affect output quality.

Service groups accept a per-service `env` object for runtime library paths. The group preserves the CUDA allocation for every child.

[← All guides](index.md)
