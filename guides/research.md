# Roleplay research and custom methods

[English](research.md) · [简体中文](zh-CN/research.md) · [日本語](ja/research.md)

A roleplay study can replace its actor, prompts and generation policy while retaining voice, rendering, conversation storage and export. Start with `configs/research.example.json` and choose one of two output modes.

## Direct performance

Set `agents.roleplay.output_mode` to `performance`. The actor generates newline-delimited JSON segments:

```json
{"text":"You remembered my favorite flowers!", "emotion":"happy", "intensity":0.5,
 "action_intent":"acknowledge", "actions":[{"name":"nod","start_s":0,"duration_s":1.6,"strength":0.5}],
 "delivery":{"tone":"warm","pace":"natural","pause_after_ms":260}}
```

The application parses segments incrementally. You can replace `prompts.performance` while retaining the `Segment` contract.

## Actor plus director

Set `output_mode` to `actor_director`. Your model produces natural dialogue and stage directions. `performance_director` converts the result into segments, with thoughts removed from speech and actions mapped to supported gestures. This allows a roleplay-specific checkpoint to retain its native response format. The pipeline buffers the actor response before the director starts; use direct performance for lower first-response latency.

The actor receives the character persona and the current conversation. Previous performance records are converted back to spoken dialogue for its context. Change `prompts.actor`, `prompts.roleplay` and the per-character persona independently. The director prompt and generation settings are configured separately. The default director uses the language requested by the user, or matches the user's message; it translates spoken content when the actor switches languages. Studies that require the actor's original language can override `prompts.performance_director` or evaluate the actor directly through `ModelGateway`.

The default actor prompt asks for concise dialogue and brief stage directions. Set `agents.roleplay.generation.max_tokens` to control reply length. For longer narration, change `prompts.actor` and `agents.roleplay.generation.max_tokens` together.

## Models, prompts and inference policy

- `models.<role>.path` selects a local checkpoint.
- `agents.<role>` selects an endpoint and model ID.
- `agents.<role>.generation` selects sampling and output length. The bundled service supports temperature, top-p, repetition penalty, seed and stop strings.
- `models.<role>.chat_template` selects a local Jinja chat-template file.
- `models.<role>.template_kwargs` controls tokenizer template options, such as Qwen thinking mode.
- The local loader uses both checkpoint and tokenizer end-of-turn tokens. `models.<role>.eos_token_id` supplies an explicit token ID or list for a custom training format.
- `prompts.<name>` selects a literal string or a UTF-8 file.

Store a configuration beside your evaluation script and point `AVATAR_MODELS_CONFIG` at it. Prompt files resolve relative to that configuration. Restart affected processes when switching deployments, then start new conversations for new conditions.

## Evaluate through the same interfaces

Use the conversation API to create an independent context per character and condition. Stream turns through HTTP NDJSON and export the complete JSON history. Exports include the text, performance metadata, timestamps and interrupted/completed state. The model gateway can also be called directly when an evaluation only needs model outputs.

```python
import asyncio
from roleplay_avatar.agents import ModelGateway

async def evaluate():
    output = []
    async for token in ModelGateway("roleplay").stream(
        "You are a patient lighthouse keeper.",
        [{"role":"user", "content":"A storm is coming. What should we do?"}],
        max_tokens=500, temperature=0.7,
    ):
        output.append(token)
    return "".join(output)

print(asyncio.run(evaluate()))
```

For comparable conditions, preserve character persona, voice reference, conversation stimuli and rendering configuration. Record checkpoint revision, prompt files and generation settings. End-to-end latency includes the actor, optional director and first speech block; report these stages separately when studying responsiveness.

## Extend a method

Implement a custom controller around `ModelGateway`, or supply a replacement service behind an existing protocol. Retrieval, memory, planning or multi-character coordination can be added before the actor call. Keep conversation ownership and turn cancellation in the orchestration layer. [Architecture](architecture.md) identifies these extension points and the contracts consumed by renderers.

[← All guides](index.md)
