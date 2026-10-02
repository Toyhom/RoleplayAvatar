# Roleplay Avatar · 镜界

This framework is intended only for roleplay dialogue research and testing; the current version is still rough.

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

Give a character a face, a voice and a conversation of its own.

Roleplay Avatar turns an image and a short description into a speaking 2D character. You can also import a complete Live2D model, choose a voice, and talk through your microphone. Dialogue carries expressions, gestures and speech delivery; each character has separate conversations with JSON export. An optional initiative agent decides when to start a conversation.

The framework connects replaceable models for roleplay, character design, speech and animation. Run them locally, use model-provider APIs, or combine both. A headless API exposes the same creation and conversation workflows for applications and research.

https://github.com/user-attachments/assets/be8b3b59-ce28-4387-8f2b-dceb23f7b65c

**30-second tour:** [English](https://github.com/user-attachments/assets/be8b3b59-ce28-4387-8f2b-dceb23f7b65c) · [简体中文](https://github.com/user-attachments/assets/556ac18a-fe2e-4d63-8d5b-b694ded76a69) · [日本語](https://github.com/user-attachments/assets/47e32f4e-94e6-4a0f-978d-8a36a8303a89)

[All guides](guides/index.md)

## Start here

| What you want to do | Guide |
| --- | --- |
| Try the interface on your computer | [Quick start](guides/quickstart.md) |
| Ask Codex or Claude Code to set it up | [Copyable AI setup instructions](guides/ai-setup.md) |
| Choose models for your hardware | [Models, presets and downloads](guides/models.md) |
| Connect DeepSeek, Qwen, OpenAI or Claude | [Providers and configuration](guides/providers.md) |
| Deploy a complete local system | [Installation](guides/setup.md) |
| Speed up local inference and reduce VRAM | [Performance](guides/performance.md) |
| Build an application or integration | [API](guides/api.md) · [Architecture](guides/architecture.md) |
| Test a roleplay checkpoint or prompting method | [Research guide](guides/research.md) |

## A CPU preview in five commands

Requires Python 3.11 and Node.js 18+.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,download]'
npm ci
npm run build
AVATAR_MODE=replay .venv/bin/python -m uvicorn roleplay_avatar.app:create_app --factory --port 18080
```

Open **http://localhost:18080**. Replay provides fixed dialogue and diagnostic audio for exploring the interface and protocol. Follow the [live setup](guides/setup.md) to enable model-generated conversations, speech and character creation.

## Create and talk

1. Choose **2D** or **3D** when creating a character. Upload an image, or import a Live2D ZIP for a 2D character.
2. Describe its personality and voice. Preview the generated voice candidates and select your favorite.
3. Start a conversation by typing or speaking. Replies drive the character's mouth, expressions and gestures.
4. Start a new conversation after the current one has content, or export the complete conversation as JSON.

[Character resources](guides/resources.md) explains native Live2D imports and the official Haru, Hiyori and RobotExpressive demonstration assets. [Voice design](guides/voice.md) explains how to shape a character's voice.

## Model choice

Hardware presets cover single-GPU configurations and larger multi-GPU deployments. The catalog includes model-family variants and pinned downloads:

```bash
.venv/bin/avatar models recommend --vram-gib 24 --gpus 1
.venv/bin/avatar models download compact --mirror --model-root /path/to/models
.venv/bin/avatar models configure compact --model-root /path/to/models
```

Per-agent configuration supports OpenAI Chat Completions, OpenAI Responses, Anthropic Messages and the bundled local protocol. Prompts, generation settings and model paths are configured independently.

## License

Original framework code is [MIT](LICENSE). Model and resource sources and licenses are listed in [NOTICE](NOTICE.md).
