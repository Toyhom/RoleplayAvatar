# 安装与部署

[English](../setup.md) · [简体中文](setup.md) · [日本語](../ja/setup.md)

vLLM、SGLang、llama.cpp 和各模块显存参数见[本地推理与性能配置](performance.md)。

CPU Web 进程协调独立模型服务。各服务使用自己的环境和 GPU 分配。实时部署通常包括对话、语音、识别、音频表情，以及角色创建工作进程。

## 1. 准备应用

安装 Python 3.11、Node.js 18+、FFmpeg、SoX、libsndfile。按[快速开始](quickstart.md)安装 Web 环境并构建前端。复制 `.local.env.example` 为 `.local.env`，填写：

```bash
AVATAR_ENV_PREFIX=/absolute/path/to/project/.venv
AVATAR_MODEL_ROOT=/absolute/path/to/models
AVATAR_MODELS_CONFIG=/absolute/path/to/project/configs/models.local.json
AVATAR_PORT=18080
```

启动脚本通过 `scripts/common.sh` 加载环境。填写实际路径后运行检查：

```bash
source scripts/common.sh
"$PYTHON" -m roleplay_avatar.cli doctor
```

检查包括权重分片索引、Diffusers 组件、下载记录中的文件大小。缺失或不完整时，重复对应下载命令补齐。

## 2. 安装模型环境

获取固定版本的实现：

```bash
source scripts/common.sh
"$PYTHON" scripts/fetch_upstreams.py --only cosyvoice qwen3_tts
git -C third_party/cosyvoice submodule update --init --recursive
```

用安装器创建独立环境。GPU 示例使用 Python 3.10，Web 和 CPU 人脸环境使用 3.11。可先用 `conda create -p /srv/envs/avatar-base310 python=3.10` 创建基础解释器，再填入以下命令：

```bash
bash scripts/install_model_env.sh vision /absolute/python3.10 /srv/envs/avatar-vision
bash scripts/install_model_env.sh qwen /absolute/python3.10 /srv/envs/avatar-qwen
bash scripts/install_model_env.sh cosyvoice /absolute/python3.10 /srv/envs/avatar-cosyvoice
bash scripts/install_model_env.sh face /absolute/python3.11 /srv/envs/avatar-face
bash scripts/install_model_env.sh portrait /absolute/python3.11 /srv/envs/avatar-portrait
bash scripts/install_model_env.sh audio2face /absolute/python3.10 /srv/envs/avatar-audio2face
```

vision 环境用于 LLM、视觉、图像生成和 Whisper；CosyVoice 使用独立 Torch 2.3.1，vision/Qwen 使用 Torch 2.8。人脸用 MediaPipe，立绘打包用 rembg/ONNXRuntime。在 `.local.env` 中设置 `AVATAR_LLM_PYTHON`、`AVATAR_VISION_PYTHON`、`AVATAR_QWEN_PYTHON`、`AVATAR_TTS_PYTHON`、`AVATAR_FACE_PYTHON`、`AVATAR_PORTRAIT_PYTHON`、`AVATAR_ASR_PYTHON`、`AVATAR_AUDIO_FACE_PYTHON`。

Live2D 导入需要人设智能体和 VoiceDesign；图片创建还需要视觉、图像、人脸和立绘环境。可选 3D 增加 asset 环境及 `configs/upstreams.lock.json` 中的 AniGen、DSINE、几何依赖。

## 3. 下载模型和资源

```bash
.venv/bin/avatar models download balanced --creation --mirror --model-root /srv/models
.venv/bin/avatar models configure balanced --creation --model-root /srv/models
source scripts/common.sh
"$PYTHON" scripts/download_face_model.py
"$PYTHON" scripts/download_audio_face_model.py
"$PYTHON" scripts/download_segmentation_model.py
"$PYTHON" scripts/fetch_demo_characters.py
```

目录下载 Hugging Face 快照；辅助脚本下载 MediaPipe、UniTalker。BiRefNet 默认放在 `$AVATAR_MODEL_ROOT/rembg/birefnet-general.onnx`，可用 `AVATAR_SEGMENTATION_MODEL_PATH` 指向现有文件。声线与示例导入见[资源](resources.md)。

## 4. 启动实时服务

以下命令作为 GPU 运行器的任务内容。共享 GPUQ 服务器按项目所属账户提交 `gpuq submit --node auto --gpus N -- ...`。根据[模型表](models.md)选择显卡数，计入并发控制服务。模型路径填实际下载目录。

```bash
"$AVATAR_LLM_PYTHON" services/llm_service.py --model /srv/models/my-chat-checkpoint --port 18110
"$AVATAR_TTS_PYTHON" services/speech_service.py --model /srv/models/my-cosyvoice3 --port 18120
"$AVATAR_ASR_PYTHON" services/whisper_service.py --model /srv/models/my-whisper --port 18140 --language auto
"$AVATAR_AUDIO_FACE_PYTHON" services/audio_face_service.py --model /srv/models/my-unitalker.onnx --port 18130
```

对话 API 配置见[供应商](providers.md)。替代语音示例：

```bash
"$AVATAR_QWEN_PYTHON" services/family_speech_service.py --backend qwen-base --model /srv/models/qwen-tts-base --port 18120
```

`qwen-custom` 还接收 `--speaker`，`cosyvoice-auto` 自动加载兼容目录。这些适配器整句合成后输出；默认 CosyVoice3 在生成中输出。

填写 Web 连接：

```bash
AVATAR_LLM_URL=http://127.0.0.1:18110
AVATAR_TTS_URL=http://127.0.0.1:18120
AVATAR_ASR_URL=http://127.0.0.1:18140
AVATAR_AUDIO_FACE_URL=http://127.0.0.1:18130
AVATAR_CREATION_RUNNER=local
```

GPUQ 集群使用 `AVATAR_CREATION_RUNNER=gpuq`；`AVATAR_CREATION_GPUS` 决定顺序创建工作进程的 GPU 数，默认 1。启动 `bash scripts/serve.sh`，访问 [http://localhost:18080](http://localhost:18080) 并查看 `/api/services`。顶部可选英文、中文、日文；创建语言随界面传入，语音识别推荐 `auto`。

模型设置在对应进程重启后生效。`scripts/demo.py` 用于已配置的三节点 GPUQ 管理部署；单服务命令和 Web 进程是可移植入口。

## 5. 纯后端

设置 `AVATAR_HEADLESS=1`，通过 `/docs`、`/openapi.json` 使用创建、对话、流式音频、转写和导出。`AVATAR_API_KEY` 开启认证。参考持久层使用一个 Uvicorn worker 和文件存储；多用户应用可在 [API](api.md) 外接身份和数据库。

## 数据与升级

`characters/` 保存角色包和声线选择，`outputs/creations/` 保存创建任务，`outputs/conversations/` 保存会话。导出的 ZIP 保留八文件契约、引用与来源。

恢复后用 `avatar validate PATH --require-assets` 验证。`scripts/split_character_modes.py` 将旧的双展示角色迁移为独立 ID，元数据备份保存在 `outputs/migrations/`。

## 验证

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
npm run build
node --test tests/*.test.mjs
python scripts/check_docs.py
```

`check_studio.py`、`check_demo_library.py`、`check_conversations.py`、`check_microphone.py`、`check_localization.py` 检查实时创建、渲染、上下文、麦克风和三语界面；结果放在 `outputs/`。

## 多个服务共享分配

复制 `configs/services.example.json` 为 `configs/services.local.json`，填写解释器与服务，加载 `.local.env`。把 `services/service_group.py --config configs/services.local.json` 作为一个 GPUQ 任务，通过 `scripts/gpu_worker.sh` 启动。子进程继承同一 CUDA 分配，各有 HTTP 端口和日志。

较大配置可参考 [services.showcase.example.json](../../configs/services.showcase.example.json)：控制、语音、识别、面部服务共用一张 80 GB GPU，70B 角色模型使用两张 80 GB GPU、端口 18112，`models.roleplay.device_map=balanced`；创建时另行分配。子进程退出会停止整组并标记失败。

三节点启动器接受 `AVATAR_SERVICE_GROUP_CONFIG`；组内控制器同时用于角色扮演时设 `AVATAR_LLM_IN_GROUP=1`。`python scripts/demo.py start --replace-changed` 比较命令、模型路径、GPU 数和配置哈希，替换变化的服务。

SSH 可用节点别名，也可通过 `AVATAR_SSH_SYSTEM2_HOST`、`AVATAR_SSH_SYSTEM2_PORT`、`AVATAR_SSH_SYSTEM2_HOST_KEY_ALIAS`（system3 同理）选择私有路由。host-key alias 对应已有可信主机密钥；连接监控器在迁移时释放旧反向转发。

[← 全部指南](index.md)
