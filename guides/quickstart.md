# Quick start

[English](quickstart.md) · [简体中文](zh-CN/quickstart.md) · [日本語](ja/quickstart.md)

Follow the four steps below to install the app, connect models and start a conversation. To have Codex or Claude Code handle the setup, copy the [AI setup instructions](ai-setup.md).

## 1. Install the application

Prepare Git, Python 3.11 and Node.js 18+. For voice and character creation, also install FFmpeg, SoX and libsndfile as described in [Installation](setup.md).

Clone the repository, then install the application and build the interface. If you already have a checkout, start from its root directory and skip the first two commands.

```bash
git clone https://github.com/Toyhom/RoleplayAvatar.git
cd RoleplayAvatar
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[download]'
npm ci
npm run build
```

## 2. Choose and configure models

| Dialogue route | What to prepare | Configuration |
| --- | --- | --- |
| Provider API | Provider account, API key and model ID | [Providers](providers.md) |
| Local models | Model weights and compatible GPU capacity | [Models and presets](models.md) · [Inference performance](performance.md) |

Speech, microphone transcription and character creation have their own model services. Configure the services for the features you want in [Installation](setup.md); dialogue can use a provider API while those services run locally.

### Provider API

Follow [Providers](providers.md) to set the endpoint, model ID and API-key environment variable for each agent in `configs/models.local.json`. Then continue to step 3.

### Local models

Ask for a hardware recommendation first. `--vram-gib` is memory **per GPU**; replace the values with your hardware:

```bash
.venv/bin/avatar models recommend --vram-gib 24 --gpus 1
```

The following example downloads and configures the `compact` preset. Replace `compact` with your selected preset and `/path/to/models` with an absolute storage path:

```bash
.venv/bin/avatar models download compact --mirror --model-root /path/to/models
.venv/bin/avatar models configure compact --model-root /path/to/models
```

- `--mirror` uses [hf-mirror.com](https://hf-mirror.com). Omit it for Hugging Face, or use `--endpoint URL` for another mirror.
- Add `--dry-run` to the download command to inspect the plan before downloading.
- For image-based creation or Live2D import with voice design, add `--creation` to both the download and configure commands.
- The configure command creates `configs/models.local.json`. To keep an existing configuration, edit it or select a new file with `--output`.

## 3. Start model services and the application

Create the deployment settings file on your first installation:

```bash
cp .local.env.example .local.env
```

Edit `.local.env` to set the application environment, model directory, absolute path to `configs/models.local.json`, service interpreters and `AVATAR_*_URL` endpoints. Reuse this file on subsequent starts.

Follow [Installation](setup.md) to prepare the selected model environments and start their services. For local dialogue, use [Performance](performance.md) to choose an inference engine and memory budget.

Check the configuration and start the app:

```bash
source scripts/common.sh
"$PYTHON" -m roleplay_avatar.cli doctor
bash scripts/serve.sh
```

Open [http://localhost:18080](http://localhost:18080). Check [/api/services](http://localhost:18080/api/services) to confirm that the services you configured are ready. Keep the service terminals running while using the app; Ctrl+C stops the foreground process in each terminal.

## 4. Create a character and talk

1. Choose **2D** or **3D**, then upload an image and a short description. For a 2D character, you can also import a complete Live2D ZIP.
2. Preview the generated voice candidates and select one. [Character resources](resources.md) also describes how to install ready-made examples.
3. Type or use the microphone to talk. Microphone input requires localhost or HTTPS and browser recording permission.
4. Interrupt speech, export the conversation as JSON, or enable proactive chatting. Each character has separate conversations; a new conversation becomes available after the current one has a substantive message.

## Common setup issues

| Symptom | Next step |
| --- | --- |
| A model path is missing | Load `.local.env` through `source scripts/common.sh`, then run `"$PYTHON" -m roleplay_avatar.cli doctor` and compare paths with the download destination. |
| A service is unavailable | Inspect its log and `/healthz`, then check `AVATAR_*_URL`. |
| An API returns 401 | Set the key variable for that agent's provider. |
| GPU memory is exhausted | Select a smaller preset or separate services across allocated GPUs; run creation separately. |
| The microphone is unavailable | Open the site on localhost or HTTPS and enable browser microphone permission. |
| A download requires authorization | Complete the model repository's access steps and pass the download credential with `--token-env HF_TOKEN`. |

[← All guides](index.md)
