# Installation and deployment

[English](setup.md) · [简体中文](zh-CN/setup.md) · [日本語](ja/setup.md)

Configure vLLM, SGLang, llama.cpp and module-specific memory settings in [Local inference and performance](performance.md).

The CPU web process coordinates independent model services. Each service can run in its own environment and GPU allocation. A typical live installation has dialogue, speech, ASR and audio-to-face services, plus a worker for creating characters.

## 1. Prepare the application

Install Python 3.11, Node.js 18+, FFmpeg, SoX and libsndfile. Install the web environment and build the UI using [Quick start](quickstart.md). Copy `.local.env.example` to `.local.env` and set:

```bash
AVATAR_ENV_PREFIX=/absolute/path/to/project/.venv
AVATAR_MODEL_ROOT=/absolute/path/to/models
AVATAR_MODELS_CONFIG=/absolute/path/to/project/configs/models.local.json
AVATAR_PORT=18080
```

The service scripts load `.local.env` through `scripts/common.sh`. JSON examples use paths you replace for your computer. `avatar doctor` checks paths and prerequisites after this environment is loaded:

```bash
source scripts/common.sh
"$PYTHON" -m roleplay_avatar.cli doctor
```

The model checks inspect shard indexes, Diffusers components and download-receipt file sizes. Missing or partial weights are listed before you start inference; repeat the corresponding download command to complete the snapshot.

## 2. Install model environments

Fetch the pinned upstream implementations:

```bash
source scripts/common.sh
"$PYTHON" scripts/fetch_upstreams.py --only cosyvoice qwen3_tts
git -C third_party/cosyvoice submodule update --init --recursive
```

Create dedicated prefixes with the environment installer. The GPU examples use Python 3.10; the web and CPU face environments use Python 3.11. For example, `conda create -p /srv/envs/avatar-base310 python=3.10` supplies `/srv/envs/avatar-base310/bin/python` as a base interpreter. Supply the base executable and a new absolute destination:

```bash
bash scripts/install_model_env.sh vision /absolute/python3.10 /srv/envs/avatar-vision
bash scripts/install_model_env.sh qwen /absolute/python3.10 /srv/envs/avatar-qwen
bash scripts/install_model_env.sh cosyvoice /absolute/python3.10 /srv/envs/avatar-cosyvoice
bash scripts/install_model_env.sh face /absolute/python3.11 /srv/envs/avatar-face
bash scripts/install_model_env.sh portrait /absolute/python3.11 /srv/envs/avatar-portrait
bash scripts/install_model_env.sh audio2face /absolute/python3.10 /srv/envs/avatar-audio2face
```

Use the vision environment for the local LLM, vision, image synthesis and Whisper. CosyVoice uses its own Torch 2.3.1 environment; vision/Qwen use Torch 2.8. CPU face detection uses MediaPipe; portrait packaging uses rembg/ONNXRuntime. Assign the resulting Python paths to `AVATAR_LLM_PYTHON`, `AVATAR_VISION_PYTHON`, `AVATAR_QWEN_PYTHON`, `AVATAR_TTS_PYTHON`, `AVATAR_FACE_PYTHON`, `AVATAR_PORTRAIT_PYTHON`, `AVATAR_ASR_PYTHON` and `AVATAR_AUDIO_FACE_PYTHON` in `.local.env`.

A native Live2D import uses the character-design agent and VoiceDesign. Image creation also uses the vision, image, face and portrait environments. Optional 3D adds the asset environment and pinned AniGen/DSINE/geometry dependencies from `configs/upstreams.lock.json`.

## 3. Download models and resources

```bash
.venv/bin/avatar models download balanced --creation --mirror --model-root /srv/models
.venv/bin/avatar models configure balanced --creation --model-root /srv/models
source scripts/common.sh
"$PYTHON" scripts/download_face_model.py
"$PYTHON" scripts/download_audio_face_model.py
"$PYTHON" scripts/download_segmentation_model.py
"$PYTHON" scripts/fetch_demo_characters.py
```

The model catalog handles Hugging Face snapshots. The auxiliary scripts fetch fixed MediaPipe and UniTalker resources. The segmentation downloader installs rembg's official BiRefNet at `$AVATAR_MODEL_ROOT/rembg/birefnet-general.onnx`; `AVATAR_SEGMENTATION_MODEL_PATH` selects an existing copy. Voice/resource installation and sample import are described in [Resources](resources.md).

## 4. Start live inference

The service commands below are the payloads for your GPU runner. On a shared GPUQ server, submit them as the project owner using `gpuq submit --node auto --gpus N -- ...`; each task keeps the queue's CUDA allocation. Choose the GPU count from the model memory table, including concurrent controller services. Model paths must resolve to downloaded checkpoint directories.

```bash
"$AVATAR_LLM_PYTHON" services/llm_service.py --model /srv/models/my-chat-checkpoint --port 18110
"$AVATAR_TTS_PYTHON" services/speech_service.py --model /srv/models/my-cosyvoice3 --port 18120
"$AVATAR_ASR_PYTHON" services/whisper_service.py --model /srv/models/my-whisper --port 18140
"$AVATAR_AUDIO_FACE_PYTHON" services/audio_face_service.py --model /srv/models/my-unitalker.onnx --port 18130
```

For a hosted dialogue model, configure [the provider](providers.md). For alternate local speech:

```bash
"$AVATAR_QWEN_PYTHON" services/family_speech_service.py --backend qwen-base --model /srv/models/qwen-tts-base --port 18120
```

`qwen-custom` also accepts `--speaker`; `cosyvoice-auto` loads a compatible CosyVoice family directory. These adapters buffer one sentence before emitting PCM; the default CosyVoice3 service streams during generation.

Connect the web process to the service URLs:

```bash
AVATAR_LLM_URL=http://127.0.0.1:18110
AVATAR_TTS_URL=http://127.0.0.1:18120
AVATAR_ASR_URL=http://127.0.0.1:18140
AVATAR_AUDIO_FACE_URL=http://127.0.0.1:18130
AVATAR_CREATION_RUNNER=local
```

Set `AVATAR_CREATION_RUNNER=gpuq` on a GPUQ cluster. `AVATAR_CREATION_GPUS` selects the allocation for the sequential creation worker; the default is one. Then run:

```bash
bash scripts/serve.sh
```

Visit http://localhost:18080 and inspect `/api/services`. Model configuration changes take effect when the corresponding service restarts. `scripts/demo.py` is the administrator launcher for a configured three-node GPUQ deployment; individual service commands and the web process provide the portable interfaces.

## 5. Backend-only deployments

Set `AVATAR_HEADLESS=1` before starting the web process. `/docs` and `/openapi.json` expose creation, conversations, streaming, microphone transcription and export APIs. Set `AVATAR_API_KEY` for backend authentication. The reference persistence layer uses one Uvicorn worker and file-backed character/conversation storage. A public multi-user application can provide its own identity and storage layers around the [API](api.md).

## Data and upgrades

`characters/` stores character packages and voice selection. `outputs/creations/` stores durable creation jobs; `outputs/conversations/` stores conversation history. Exported ZIP packages preserve the character's eight-file contract, asset references and provenance.

Validate a restored package with `avatar validate PATH --require-assets`. `scripts/split_character_modes.py` migrates an older dual-presentation package into separate character IDs, preserving a metadata backup in `outputs/migrations/`.

## Verify the installation

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
npm run build
node --test tests/actions.test.mjs
```

The browser scripts `check_studio.py`, `check_demo_library.py`, `check_conversations.py` and `check_microphone.py` exercise the live creation, rendering, context and microphone flows. Their outputs stay under `outputs/`.

## Share one allocated GPU between services

Copy `configs/services.example.json` to `configs/services.local.json`, select the required services and their interpreter paths, and load `.local.env`. `services/service_group.py --config configs/services.local.json` starts the group inside your current GPU allocation. In GPUQ, submit that command as one task using the project's `scripts/gpu_worker.sh` wrapper. Children inherit the same CUDA allocation and keep independent HTTP ports and log files.

For the `showcase` preset, use [services.showcase.example.json](../configs/services.showcase.example.json). It runs the Qwen controller, speech, recognition and facial-expression services on one 80 GB allocation. A 70B actor runs separately on two 80 GB GPUs at port 18112. Set `models.roleplay.device_map` to `balanced` to distribute its weights across both GPUs. This layout matches the three-GPU recommendation; character creation uses a separate allocation when needed.

If a child exits, the supervisor stops the group so the job's failure is visible. Set each module's URL to its port as usual. The three-node launcher also accepts `AVATAR_SERVICE_GROUP_CONFIG`; set `AVATAR_LLM_IN_GROUP=1` when the group's controller is also the roleplay model. A separate actor keeps its own allocation.

The launcher compares service commands and group configuration hashes before reuse. `python scripts/demo.py start --replace-changed` replaces services whose model path, command, GPU count or group configuration changed.

SSH routes use each node's configured alias. A private route can be selected with `AVATAR_SSH_SYSTEM2_HOST`, `AVATAR_SSH_SYSTEM2_PORT` and `AVATAR_SSH_SYSTEM2_HOST_KEY_ALIAS` (or the corresponding `SYSTEM3` names). The host-key alias identifies the existing trusted server key. The launcher records the route for its connection watcher and releases obsolete reverse forwards when services move between nodes.

[← All guides](index.md)
