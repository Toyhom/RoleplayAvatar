# Providers and configuration

[English](providers.md) · [简体中文](zh-CN/providers.md) · [日本語](ja/providers.md)

Configure vLLM, SGLang, llama.cpp and module-specific memory settings in [Local inference and performance](performance.md).

Each agent chooses its own provider, model, generation settings and prompt. A general model can serve all agents, or a specialized actor can work with a separate controller.

## Connect one provider

Create `configs/models.local.json`:

```json
{
  "agents": {
    "default": {"provider": "qwen", "model": "qwen-plus", "require_key": true,
                "extra_body": {"enable_thinking": false}}
  }
}
```

Set the configuration path and credential in your shell or private `.local.env`:

```bash
export AVATAR_MODELS_CONFIG="$PWD/configs/models.local.json"
export DASHSCOPE_API_KEY='your-key'
```

Restart the web process to apply agent configuration. Creation workers read the configuration when a new task starts.

| Provider | Protocol | Default URL | Key variable |
| --- | --- | --- | --- |
| `deepseek` | OpenAI Chat Completions | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |
| `qwen` | OpenAI Chat Completions | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` |
| `openai` | OpenAI Chat Completions | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| `anthropic` / `claude` | Anthropic Messages | `https://api.anthropic.com/v1` | `ANTHROPIC_API_KEY` |
| `openai-compatible` | OpenAI Chat Completions | `http://127.0.0.1:8000/v1` | `AVATAR_LLM_API_KEY` |
| `local` | `/chat` NDJSON | `http://127.0.0.1:18110` | `AVATAR_LLM_API_KEY`, optional |

Set `model` to an ID available in your account. Override `url` for regional endpoints, proxies, vLLM, SGLang or llama.cpp. Set `require_key: false` for a local endpoint that accepts requests without authentication.

## Route modules independently

```json
{
  "agents": {
    "default": {"provider": "qwen", "model": "qwen-plus"},
    "roleplay": {"provider": "openai-compatible", "url": "http://localhost:8000/v1",
                 "model": "my-roleplay-checkpoint", "output_mode": "actor_director", "require_key": false},
    "performance_director": {"generation": {"temperature": 0.2}},
    "initiative": {"provider": "deepseek", "model": "deepseek-chat"},
    "character_design": {"provider": "anthropic", "model": "YOUR_CLAUDE_MODEL_ID"},
    "voice_direction": {"provider": "openai", "model": "YOUR_OPENAI_MODEL_ID"}
  }
}
```

`agents.<role>` overrides `agents.default`. Naming a new provider resets the inherited endpoint, key variable, model and provider-specific generation extensions; specify its model explicitly. Fields within `generation` and `extra_body` merge for agents that retain the same provider.

The `performance` output mode asks the roleplay model to produce playable JSON directly. `actor_director` lets it produce natural roleplay text, then sends that text to `performance_director` for speech, expression and gesture extraction. [Research configuration](research.md) explains both modes.

## Generation and protocol options

`generation` accepts settings such as `temperature`, `top_p`, `max_tokens`, `seed` and supported provider parameters. Configured values override call defaults. Set a value to `null` to omit it, for example `temperature` on a model that uses a fixed sampling policy.

`extra_body` carries vendor extensions, such as Qwen's `enable_thinking`. Message, model and routing fields are owned by the gateway. Reasoning deltas are kept separate from spoken text.

For OpenAI Responses:

```json
{"provider":"openai", "backend":"openai-responses", "model":"YOUR_MODEL_ID",
 "generation":{"temperature":null, "max_tokens":1400}}
```

The gateway maps `max_tokens` to `max_output_tokens`. For Chat Completions models using `max_completion_tokens`, set `max_tokens_field: "max_completion_tokens"`. Anthropic uses its native `/messages` request, `x-api-key` and streaming text events. `timeout_s` changes the response timeout.

Add organization-specific providers under `providers`:

```json
{"providers":{"lab":{"backend":"openai","url":"https://models.example.org/v1",
                        "api_key_env":"LAB_MODEL_KEY"}},
 "agents":{"default":{"provider":"lab","model":"research-model"}}}
```

## Image understanding through an API

```json
{"models":{"vision":{"adapter":"api"}},
 "agents":{"vision":{"provider":"qwen","model":"qwen-vl-plus"}}}
```

The creation worker sends the uploaded image and design prompt to this vision agent. OpenAI-compatible and Anthropic image messages are supported. Image synthesis and speech use their own adapters and URLs; their contracts are described in [Architecture](architecture.md).

## Prompt files

`prompts` accepts literal text or a file, resolved relative to the JSON configuration:

```json
{"prompts":{"actor":{"file":"../prompts/local/actor.txt"},
            "initiative":"Decide whether a brief follow-up would suit this conversation."}}
```

Default prompts are in `src/roleplay_avatar/prompt_templates/`. Configurable names include `roleplay`, `actor`, `performance`, `performance_director`, `initiative`, `character_design`, `voice_direction`, `vision`, `image_2d` and `image_3d`. Vision templates accept `{description}`; image templates accept `{appearance}`. Character-specific persona remains part of each character package.

Complete examples: [mixed providers](../configs/providers.example.json), [research](../configs/research.example.json), [all model paths](../configs/models.example.json).

[← All guides](index.md)
