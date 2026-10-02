# 模型、硬件与下载

[English](../models.md) · [简体中文](models.md) · [日本語](../ja/models.md)

模型路径选择检查点，适配器实现推理，智能体选择本地或远程接口。[机器可读目录](../../src/roleplay_avatar/data/models.json)记录仓库 ID、固定版本、适配器、许可和预计显存。

## 硬件预设

预设预算包含同时运行的对话、语音、识别；角色创建单独运行，逐阶段加载模型。

| 预设 | 建议硬件 | 对话 | 语音识别 |
| --- | --- | --- | --- |
| API | 小 GPU 或远程语音服务 | 自选供应商 | 配置的本地/远程 ASR |
| `compact` | 1 × 24 GB | Qwen3-4B | Whisper-small |
| `balanced` | 1 × 40–48 GB | Qwen3-8B | Whisper-large-v3-turbo |
| `quality` | 2 × 80 GB | Qwen3-32B | Whisper-large-v3 |
| `showcase` | 3 × 80 GB | CoSER-70B + Qwen3-8B 控制器 | Whisper-large-v3-turbo |

四种本地预设均使用 CosyVoice3。最大预设把角色权重分配到两张 GPU，其他服务使用独立分配。显存估计含上下文和激活余量，受长度、分辨率、批量与精度影响。

```bash
avatar models list
avatar models recommend --vram-gib 48 --gpus 1
avatar models download balanced --model-root /srv/models --dry-run
avatar models download balanced --model-root /srv/models --mirror
avatar models configure balanced --model-root /srv/models --output configs/models.local.json
```

`--vram-gib` 是单张 GPU 显存。配置命令创建新文件；用 `AVATAR_MODELS_CONFIG` 指向其绝对路径，重启对应服务。[安装](setup.md)说明解释器和服务地址。

## 镜像与固定版本下载

`--mirror` 使用 `https://hf-mirror.com`，`--endpoint URL` 选择其他 Hugging Face 兼容源。下载固定上游 commit，支持续传，保留仓库文档并校验 LFS SHA256。模型旁边的 `.avatar-download.json` 记录下载来源、版本与校验信息。

```bash
avatar models download qwen3-8b --mirror --model-root /srv/models
avatar models download qwen3-vl-32b --mirror --model-root /srv/models
```

给预设加 `--creation` 可下载图像理解、绘图、声线设计。quality/showcase 选择 Qwen3-VL-32B 和 Qwen-Image-Edit-2511；使用该编辑器时设置 `AVATAR_IMAGE_BACKEND=qwen_image`，口型参考仍使用 FLUX。

访问受限仓库时，先完成上游授权，再通过 `--token-env HF_TOKEN` 指定凭据。凭据发往所选下载端点。失败后重复命令即可续传。安装下载组件用 `python -m pip install -e '.[download]'`。`scripts/download_snapshot.py` 提供额外的分段下载入口，接收仓库、版本和根目录，并遵循 `HF_ENDPOINT`。

## 模块与系列适配

| 模块 | 支持系列 | 适配方式 |
| --- | --- | --- |
| 角色与文字智能体 | Qwen3 dense/MoE、CoSER Llama 3.1、兼容 causal-LM | `llm_service.py`，AutoModelForCausalLM，自定义模板，多 GPU，可选 int4/int8 |
| 远程智能体 | DeepSeek、Qwen、OpenAI、Claude、兼容服务器 | Chat Completions、Responses、Anthropic Messages |
| 图像理解 | Qwen3-VL dense/MoE、兼容图文模型 | AutoModelForImageTextToText 或视觉 API |
| 图像扩展、口型参考 | FLUX.2 klein 4B/9B | Flux2KleinPipeline，图像条件 |
| 图像扩展 | Qwen-Image-Edit-2511 与兼容 Edit Plus | QwenImageEditPlusPipeline |
| 声线设计 | Qwen3-TTS 1.7B VoiceDesign | 自然语言设计参考声线 |
| 实时语音 | CosyVoice3 0.5B | `speech_service.py`，流式生成、参考条件与语调 |
| 替代语音 | CosyVoice 300M/2/3；Qwen3-TTS Base、CustomVoice 0.6/1.7B | `family_speech_service.py`，整句缓冲，克隆或命名说话人 |
| 麦克风 | Whisper tiny/base/small/medium/large-v3/turbo | `whisper_service.py`，自动检测语言或 `--language` |
| 前景 | BiRefNet-general ONNX / rembg | `segmentation` 路径 |
| 人脸点位 | MediaPipe FaceLandmarker | `face_landmarker` 的 `.task` |
| 音频表情 | UniTalker v0.4.0 base ONNX | `audio_face`，通道映射见配置 |
| 可选 3D | AniGen、DINOv2 ViT-L/14 registers、DSINE/EfficientNet-B5 | AniGen 与 `dinov2`、`normals` 目录 |

`tested` 表示已验证的推理适配，`adapter-compatible` 表示系列加载器和任务接口兼容。MoE 显存取决于全部参数，激活参数量主要描述每 token 计算量。固定 ONNX/task 资源按输出契约匹配。VoiceDesign、Base、CustomVoice 是不同任务，详见[声音](voice.md)。

## 模型路径和加载选项

优先级：`AVATAR_<ROLE>_MODEL_PATH` → `models.<role>.path` → `AVATAR_MODEL_ROOT` 加仓库与版本。支持 `~` 和环境变量；模型路径相对进程工作目录，提示词和模板相对配置文件。

```json
{"models":{
 "roleplay":{"path":"/srv/models/my-checkpoint","device_map":"auto","dtype":"bfloat16",
             "context":8192,"quantization":"none","template_kwargs":{"enable_thinking":false}},
 "vision":{"path":"/srv/models/my-vl-checkpoint"},
 "tts":{"path":"/srv/models/my-cosyvoice"},
 "asr":{"path":"/srv/models/my-whisper"}}}
```

`repo`、`revision`、`license` 描述自定义权重，下载记录自动识别目录内模型身份，创建阶段和导出的角色包保留实际模型记录。`quantization` 支持 `int4`、`int8`、`none`，量化需要该模型环境安装兼容 bitsandbytes。GGUF/AWQ/GPTQ 可通过 OpenAI 兼容服务连接。自动分配只使用进程可见的 GPU。

还可指定 `image`、`image_edit`、`voice_design`、`voice_clone`、`mesh`、`normals`、`dinov2`、`audio_face`、`segmentation`、`face_landmarker`。tokenizer、语音编码器、flow、vocoder 从父模型目录加载。辅助资源 URL 和哈希见 `configs/*models.lock.json` 与 `configs/audio-face-model.lock.json`。

新系列可以扩展已有适配器，或实现[架构](architecture.md)中的文本、音频、转写、面部系数或创建阶段契约。

## 各型号显存参考

表中为显存规划估算，单位 GiB；并发部署须另加其他服务。Dense LLM 以 16 位权重加上下文余量估算，图像编辑可能使用 CPU 卸载并增加内存需求。固定人脸与前景阶段可在 CPU 运行，内存随图片大小变化。

| 模块 | 目录 ID | 显存 (GiB) | 验证状态 |
| --- | --- | --- | --- |
| `asr` | `whisper-base` | 1 | adapter-compatible |
| `asr` | `whisper-tiny` | 1 | adapter-compatible |
| `asr` | `whisper-small` | 2 | tested |
| `asr` | `whisper-large-v3-turbo` | 4 | tested |
| `asr` | `whisper-medium` | 4 | adapter-compatible |
| `asr` | `whisper-large-v3` | 7 | adapter-compatible |
| `image` | `flux2-klein-4b` | 18 | tested |
| `image` | `flux2-klein-9b` | 32 | adapter-compatible |
| `image_edit` | `qwen-image-edit-2511` | 48 | tested |
| `mesh` | `anigen` | 45 | tested |
| `roleplay` | `qwen3-0.6b` | 3 | adapter-compatible |
| `roleplay` | `qwen3-1.7b` | 5 | adapter-compatible |
| `roleplay` | `qwen3-4b` | 10 | adapter-compatible |
| `roleplay` | `coser-8b` | 20 | tested |
| `roleplay` | `qwen3-8b` | 20 | tested |
| `roleplay` | `qwen3-14b` | 34 | adapter-compatible |
| `roleplay` | `qwen3-30b-a3b` | 70 | adapter-compatible |
| `roleplay` | `qwen3-32b` | 74 | adapter-compatible |
| `roleplay` | `coser-70b` | 152 | tested |
| `roleplay` | `qwen3-235b-a22b` | 510 | adapter-compatible |
| `tts` | `cosyvoice1` | 4 | adapter-compatible |
| `tts` | `qwen-tts-0.6b-base` | 4 | adapter-compatible |
| `tts` | `qwen-tts-0.6b-customvoice` | 4 | adapter-compatible |
| `tts` | `cosyvoice2` | 6 | adapter-compatible |
| `tts` | `cosyvoice3` | 6 | tested |
| `tts` | `qwen-tts-1.7b-base` | 8 | tested |
| `tts` | `qwen-tts-1.7b-customvoice` | 8 | adapter-compatible |
| `vision` | `qwen3-vl-2b` | 7 | adapter-compatible |
| `vision` | `qwen3-vl-4b` | 12 | tested |
| `vision` | `qwen3-vl-8b` | 24 | adapter-compatible |
| `vision` | `qwen3-vl-30b-a3b` | 72 | adapter-compatible |
| `vision` | `qwen3-vl-32b` | 76 | tested |
| `vision` | `qwen3-vl-235b-a22b` | 530 | adapter-compatible |
| `voice_design` | `qwen-voice-design` | 8 | tested |

[← 全部指南](index.md)
