# 本地推理与性能配置

[English](../performance.md) · [简体中文](performance.md) · [日本語](../ja/performance.md)

各本地模型服务使用独立的推理环境和显存预算。使用同一检查点的智能体可以共享服务，让角色对话、主动交互判断和角色设定扩写复用一份权重。模型厂商 API 继续使用[提供商配置](providers.md)。

## 选择推理后端

| 模块 | 后端 | 主要优化项 |
| --- | --- | --- |
| 对话与控制智能体 | vLLM | 连续批处理、前缀缓存、分块预填充、张量并行、权重与 KV 缓存量化 |
| 对话与受支持的视觉模型 | SGLang | 连续批处理、RadixAttention 前缀缓存、张量并行和量化 |
| GGUF 对话模型 | llama.cpp `llama-server` | 权重与 KV 缓存量化、部分层卸载到 GPU、CPU/GPU 推理、并行槽位 |
| Transformers 对话 | 内置 `llm_service.py` | SDPA、BF16/FP16、bitsandbytes INT4/INT8、设备映射 |
| Whisper 语音识别 | faster-whisper / CTranslate2 | FP16/INT8、搜索束宽、CPU/GPU 选择 |
| Qwen3-TTS | 原生 Torch | SDPA / FlashAttention 2、计算精度、参考声线条件缓存 |
| CosyVoice3 | 原生后端 / TensorRT | 流式合成、FP16、TensorRT flow 引擎 |
| 图像生成 | Diffusers / Accelerate | 模型或逐层 CPU 卸载、VAE 分块与切片、可选编译 |
| 音频驱动表情 | ONNX Runtime | 独立的 CUDA 推理服务 |

模型架构和量化格式的兼容性取决于后端版本与 GPU。选择检查点时参考 [vLLM](https://docs.vllm.ai/en/latest/models/supported_models.html)、[SGLang](https://docs.sglang.ai/supported_models/generative_models.html)、[llama.cpp](https://github.com/ggml-org/llama.cpp) 的支持列表。视觉模型通过 `agents.vision` 和 `models.vision.adapter="api"` 使用图像消息接口。

## 使用 vLLM 启动

创建独立的 Python 3.11 环境并生成配置：

```bash
bash scripts/install_model_env.sh vllm /absolute/python3.11 /srv/envs/avatar-vllm
.venv/bin/avatar models configure compact --engine vllm \
  --inference-python /srv/envs/avatar-vllm/bin/python \
  --model-root /srv/models --output configs/models.local.json
export AVATAR_MODELS_CONFIG="$PWD/configs/models.local.json"
.venv/bin/avatar inference plan --role roleplay
```

按[模型目录](models.md)下载权重。`inference plan` 显示实际启动命令与对应的智能体连接配置。把以下命令交给 GPU 运行器执行：

```bash
.venv/bin/avatar inference start --role roleplay
```

共享 GPUQ 服务器上，用自己的账号提交：`gpuq submit --node auto --gpus N -- /absolute/path/to/.venv/bin/avatar inference start --role roleplay`。进程继承调度器分配的 CUDA 设备；`tensor_parallel` 应与分配的 GPU 数量匹配。排队任务使用解释器的绝对路径。

安装器使用 `requirements/vllm.txt` 的固定版本，并在新环境中记录已安装包。推理环境拥有独立的 Torch 依赖，CPU 应用继续使用 `.venv`。选择 SGLang 时，将安装器类型与 `--engine` 都改为 `sglang`。

自动生成的 vLLM 预设使用原生算子与解码 CUDA graph，缩短冷启动时间。删除 `extra_args` 中的 `--compilation-config` 覆盖项，即可使用 vLLM 默认的 Torch 编译。多卡预设使用 NCCL 通信。

vLLM 安装器同时注册框架的设备插件；使用 vLLM 0.21 时，它通过 NVML 解析已分配的 GPU UUID，并保持 `CUDA_VISIBLE_DEVICES` 不变。 多卡使用 UUID 分配时，在 `extra_args` 中加入 `"--disable-custom-all-reduce"`，使用 NCCL 通信。

## 显存与并发

从 [inference.example.json](../../configs/inference.example.json) 开始配置：`models` 选择权重，`inference` 定义本地进程，`agents` 指定请求路由。多个智能体可以连接同一个推理进程。`avatar doctor` 检查配置和本地路径。

| 参数 | 含义与起始建议 |
| --- | --- |
| `context` | 每个请求的提示词加输出 token 上限，可从 4096–8192 开始。 |
| `gpu_memory_utilization` | vLLM 的每卡显存预算；SGLang 的静态显存比例。为语音、识别及临时分配留出空间。 |
| `max_sequences` | 同时活跃的请求数；交互应用可从 1–4 开始。 |
| `max_batch_tokens` | vLLM 每批 token 预算 / SGLang 预填充分块大小，可从 2048 开始。 |
| `prefix_caching` | 复用角色设定和提示词的相同前缀。 |
| `chunked_prefill` | 分批处理长提示词，让正在生成的回复继续推进。 |
| `tensor_parallel` | 在分配到的多张 GPU 上切分一个模型。 |
| `quantization` | 后端支持的权重量化格式，例如 `awq`、`gptq`、`fp8`，需匹配检查点与运行时。 |
| `kv_cache_dtype` | 与权重精度独立的 KV 缓存精度；支持的 vLLM/SGLang 环境可选择 `fp8`。 |
| `cpu_offload_gb` | 引擎管理的权重卸载量，节约显存并增加 CPU/GPU 数据传输。 |
| `enforce_eager` | 关闭 CUDA graph，以吞吐换取更低的图缓存占用。 |
| `chat_template`、`template_kwargs` | 模型专用对话模板和生成模式参数。 |
| `extra_args` | 用 JSON 字符串数组传入额外的原生启动参数。 |

显存包括权重、KV 缓存、CUDA graph、激活和其他服务。下面是十进制 GB 的**纯权重理论值**：

| 参数量 | 16 位 | 8 位 | 4 位 |
| --- | ---: | ---: | ---: |
| 4B | 8 | 4 | 2 |
| 8B | 16 | 8 | 4 |
| 32B | 64 | 32 | 16 |
| 70B | 140 | 70 | 35 |

量化还需要缩放因子和元数据。KV 缓存随上下文与并发数增长。较大的预分配缓存会让高吞吐引擎比单请求 Transformers 服务占用更多显存；与语音共卡时，应降低其预算。角色创建适合单独分配 GPU 或错峰运行。

vLLM 可通过 `extra_args: ["--compilation-config", "{\"mode\":0}"]` 使用原生算子，并关闭 Torch 编译和 CUDA graph。需要保留解码阶段的 CUDA graph 时，将配置改为 `{"mode":0,"cudagraph_mode":"FULL_DECODE_ONLY"}`。权重放在网络文件系统时，可追加 `["--safetensors-load-strategy", "eager"]`，启动时顺序读取每个分片；这会增加临时主机内存占用。

对于兼容的 BF16/FP16 权重，vLLM 可通过 `quantization="fp8"` 在加载时量化。设置 `kv_cache_dtype="fp8"` 可压缩缓存，在 `extra_args` 中追加 `"--calculate-kv-scales"` 可计算缓存缩放因子。选择支持 vLLM FP8 算子的 GPU，再降低显存预算，实测输出质量和可用容量。

## GGUF 与小显存机器

安装或编译适合自己设备的 [llama-server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)。把 `models.roleplay.path` 指向 GGUF 文件，在 `inference.roleplay` 中填写：

```json
{
  "engine": "llama.cpp", "executable": "/srv/llama.cpp/build/bin/llama-server",
  "served_model": "avatar-roleplay", "port": 18110,
  "context": 4096, "max_sequences": 1, "gpu_layers": -1,
  "kv_cache_dtype": "q8_0"
}
```

智能体使用示例中的 OpenAI 兼容连接配置。`gpu_layers=0` 使用 CPU；较小的正数将部分层放到 GPU。权重量化由 GGUF 文件决定。启动器按 `context × max_sequences` 分配 llama.cpp 并行槽位的总上下文；其他原生参数放入 `extra_args`。

## 语音与图像优化

**语音识别：** 安装 `faster-whisper` 环境，使用 CTranslate2 格式的 Whisper 权重。已有 Transformers 权重可在装有 CTranslate2、Transformers 和 Torch 的环境中转换：

```bash
ct2-transformers-converter --model /srv/models/whisper \
  --output_dir /srv/models/whisper-ct2 --quantization float16 \
  --copy_files tokenizer.json preprocessor_config.json
/srv/envs/avatar-faster-whisper/bin/python services/faster_whisper_service.py \
  --model /srv/models/whisper-ct2 --compute-type int8_float16 --port 18140
```

服务在就绪前完成预热，`--no-warmup` 可跳过。它保持现有麦克风 `/transcribe` 协议与自动语言检测。`--beam-size 1` 优先考虑延迟，增加束宽可改善识别；CPU 使用 `--device cpu --compute-type int8`。[faster-whisper](https://github.com/SYSTRAN/faster-whisper) 文档列出 CTranslate2 的 CUDA/cuDNN 要求。

**Qwen3-TTS：** `family_speech_service.py --backend qwen-base` 默认缓存八份参考声线条件。修改参考音频或文本会使对应缓存失效。`--voice-cache-size 0` 关闭缓存，`/healthz` 显示命中次数。`--attention sdpa` 使用原生注意力；安装匹配的 FlashAttention 后可用 `--attention flash_attention_2`，`--dtype` 控制精度。音频按句生成，再以连续的 24 kHz PCM 分块发送。

**CosyVoice3：** `speech_service.py --fp16` 启用原生半精度路径，`--tensorrt` 启用上游 flow 引擎。匹配的 TensorRT 依赖安装在独立环境中；引擎在目标 GPU 上首次启动时构建，其产物随该部署保留。参见 [CosyVoice](https://github.com/FunAudioLLM/CosyVoice)。

**图像：** `models.image.offload` 或 `models.image_edit.offload` 支持 `model`（默认）、`sequential`（降低驻留显存，增加传输）、`none`（全部驻留 GPU）。VAE 支持时，`vae_tiling` 和 `vae_slicing` 默认开启。`compile=true` 配合 `offload="none"` 启用 Torch 编译，适合反复使用相同尺寸的服务，会增加冷启动时间。创建流程通常为每个阶段启动独立进程。

## 测量自己的部署

比较引擎时，保持提示词、模型、上下文和输出上限一致：

```bash
.venv/bin/python scripts/benchmark_inference.py \
  --url http://127.0.0.1:18110/v1 --model avatar-roleplay \
  --requests 8 --concurrency 4 --max-tokens 128 \
  --template-kwargs '{"enable_thinking":false}' \
  --output outputs/benchmarks/vllm-c4.json
```

内置 Transformers 服务使用 `--backend local --url http://127.0.0.1:18110`。`--warmups` 设置按目标并发数执行的预热批次数，预热请求不计入结果。结果记录预热后的首段文字延迟、总延迟、失败数、输出字符数及服务端报告的 token 吞吐。通过 `--prompt` 和并发参数模拟实际负载。量化和计算精度会影响输出质量，调速时也应验证打断和语音可懂度。

服务组中的每个服务都可以通过 `env` 对象配置运行库路径；子进程保持调度器分配的 CUDA 设备。

[← 所有指南](index.md)
