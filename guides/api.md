# Backend API

[English](api.md) · [简体中文](zh-CN/api.md) · [日本語](ja/api.md)

Set `AVATAR_HEADLESS=1` to serve the API. The same routes power the browser studio. Interactive endpoint schemas are at `/docs`; OpenAPI is at `/openapi.json`. Set `AVATAR_API_KEY` and send `Authorization: Bearer KEY` when API authentication is enabled.

## Start a conversation and stream a reply

Create a client identity with `POST /api/conversations/client`. Keep its returned cookie or send the returned `client_id` in `X-Avatar-Client`. The identity grants access to that client's conversation history.

```python
import json
import uuid
import httpx

with httpx.Client(base_url="http://127.0.0.1:18080", timeout=180, trust_env=False) as client:
    identity = client.post("/api/conversations/client").json()["client_id"]
    client.headers["X-Avatar-Client"] = identity
    character = client.get("/api/characters").json()[0]["profile"]["character_id"]
    conversation = client.post("/api/conversations", json={"character_id": character}).json()
    with client.stream("POST", "/api/turns", json={
        "type": "speak", "turn_id": uuid.uuid4().hex,
        "character_id": character, "conversation_id": conversation["id"],
        "text": "How has your day been?"
    }) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            event = json.loads(line)
            if event["type"] == "text":
                print(event["data"]["text"])
```

Events include `turn_start`, `stream_start`, `text`, `audio`, `motion`, `face`, `stream_end`, `turn_end`, `cancelled` and `error`. Text carries per-segment performance. Audio contains base64-encoded 24 kHz mono PCM16 little-endian data. `sample_offset` is the cumulative audio sample count; `sequence` increases monotonically. Synchronize playback against the audio sample clock.

`POST /api/turns/{turn_id}/cancel` cancels a client's turn. Disconnecting the HTTP stream also cancels it. `/ws` supports the same event protocol; send a `SpeakRequest` or `{"type":"cancel","turn_id":"..."}`. Interrupted replies remain in the exported history with their completion status.

## Conversations and initiative

| Route | Purpose |
| --- | --- |
| `POST /api/conversations` | Create or reuse an empty conversation for the chosen character |
| `GET /api/conversations?character_id=ID` | List the client's conversations, including `has_content` |
| `GET /api/conversations/{id}` | Messages, performance, status and initiative settings |
| `GET /api/conversations/{id}/export` | JSON download with timestamps and complete/interrupted state |
| `PATCH /api/conversations/{id}/initiative` | Set `enabled`, `idle_seconds` (10–600), `cooldown_seconds` (30–3600) |
| `POST /api/conversations/{id}/initiative/check` | Submit `idle_seconds`, `visible`, `typing`, `recording`, `playing` |

An approved initiative check returns `topic` and `ticket`. Submit a turn with `source="initiative"`, `initiative_ticket=ticket` and the topic as `text`. The server consumes the ticket and uses its stored topic. Tickets expire after 45 seconds or a context change. Clients should check typing/recording state again before submitting.

## Character creation

`POST /api/creations` accepts:

```json
{"description":"An adult florist with a warm voice and a playful sense of humor",
 "locale":"en", "image_base64":"...", "presentation":"2d", "voice_candidates":5, "seed":42}
```

`presentation` is `2d` or `3d`. `locale` selects `en`, `zh-CN` or `ja` for persona and voice design, defaulting to `zh-CN`. Images are PNG/JPEG/WebP, up to 10 MB, with a minimum side of 128 pixels. Voice candidates range from 3 to 8. The response is HTTP 202 with a durable job ID.

`POST /api/characters/import-live2d?description=...&voice_candidates=5&locale=en` accepts an `application/zip` body. The limits are 128 MB compressed, 512 MB expanded and 4096 files. Select `model_entry=path/to/model.model3.json` for a ZIP containing multiple models. See [resource structure](resources.md).

| Route | Purpose |
| --- | --- |
| `GET /api/studio` | Creation availability and stages |
| `GET /api/creations`, `GET /api/creations/{id}` | Job state, progress, result character |
| `POST /api/creations/{id}/cancel`, `.../retry` | Cancel or resume a job |
| `GET /api/characters`, `GET /api/characters/{id}` | Character catalog and contract |
| `PATCH /api/characters/{id}` | Update `display_name` and `persona` |
| `GET /api/characters/{id}/studio` | Persona, voices and provenance |
| `GET /api/characters/{id}/voice/{candidate}` | Candidate WAV |
| `POST /api/characters/{id}/voice` | Select `{"candidate":2}` for subsequent turns |
| `GET /api/characters/{id}/export` | Complete character ZIP |
| `POST /api/transcribe` | 0.2–30 seconds of 16 kHz mono PCM16 (`pcm_base64`, `sample_rate`) |
| `GET /api/agents` | Agent roles and model choices |
| `POST /api/agents/character-design` | `description`, `locale` → `CharacterDesign` |
| `POST /api/agents/voice-direction` | `text`, optional `persona` → `Delivery` |
| `GET /api/services`, `GET /healthz` | Service/application readiness |

Machine-readable character contracts are in `schemas/`. Model service boundaries and extension points are described in [Architecture](architecture.md).

[← All guides](index.md)
