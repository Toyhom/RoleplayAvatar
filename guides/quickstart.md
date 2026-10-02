# Quick start

[English](quickstart.md) · [简体中文](zh-CN/quickstart.md) · [日本語](ja/quickstart.md)

Choose an entry point based on your goal.

| Route | Hardware | Result |
| --- | --- | --- |
| CPU preview | Python 3.11, Node.js 18+ | Interface, conversations and protocol replay |
| Hosted models | API access; a speech service for audio | Live roleplay with your provider |
| Local models | NVIDIA GPU; see the presets | Local chat, speech, microphone input and creation |

## 1. Install the web application

Run these commands from the repository directory:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,download]'
npm ci
npm run build
AVATAR_MODE=replay .venv/bin/python -m uvicorn roleplay_avatar.app:create_app --factory --port 18080
```

Visit http://localhost:18080. Select a built-in illustrated character and send a message. This route uses fixed text and a diagnostic tone. Stop the server with Ctrl+C before changing to live mode.

## 2. Choose your live configuration

For hosted dialogue, select a provider in [Providers](providers.md). Real-time audio uses the [speech service](setup.md); model APIs and the speech service may run on separate machines.

For local models, first request a recommendation. `--vram-gib` is memory **per GPU**:

```bash
.venv/bin/avatar models recommend --vram-gib 24 --gpus 1
.venv/bin/avatar models download compact --mirror --model-root /path/to/models --dry-run
```

Remove `--dry-run` to download. The `--mirror` option uses **https://hf-mirror.com**. Omit it for Hugging Face, or use `--endpoint URL`. Downloading a preset gets chat, speech and ASR weights; `--creation` adds the large image and voice-design models.

Continue with [Installation](setup.md), which covers model environments, resource installation and service startup. You can also copy [these instructions](ai-setup.md) into Codex or Claude Code to have it perform the setup.

## 3. Use the studio

Create a character from an image and description, or upload a complete Live2D ZIP. Choose 3–8 voice candidates, listen, and select one. Each character uses a single presentation type and has an independent conversation list.

Use the microphone on localhost or HTTPS. You can interrupt speech, export conversations, and enable proactive chatting per conversation. A new empty conversation is reused until it contains a substantive message.

## Common setup issues

| Symptom | Next step |
| --- | --- |
| A model path is missing | Run `avatar doctor` after loading your deployment environment; compare the path with the download destination. |
| Live services show unavailable | Inspect the service log and its `/healthz`, then check `AVATAR_*_URL`. |
| An API returns 401 | Set the key variable for that agent's provider. |
| GPU memory is exhausted | Select a smaller preset or move services to separate allocated GPUs; run creation separately. |
| The microphone is unavailable | Open the site on localhost or HTTPS and enable browser microphone permission. |
| Download access is gated | Follow the repository's access flow and select the download credential with `--token-env HF_TOKEN`. |

[← All guides](index.md)
