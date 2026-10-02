# 后端 API

[English](../api.md) · [简体中文](api.md) · [日本語](../ja/api.md)

设置 `AVATAR_HEADLESS=1` 即可仅提供 API。浏览器界面使用同一套接口。`/docs` 提供交互式说明，`/openapi.json` 提供 OpenAPI。设置 `AVATAR_API_KEY` 后，请求须携带 `Authorization: Bearer KEY`。

## 创建会话并流式接收回复

先请求 `POST /api/conversations/client`，保留返回的 Cookie，或把 `client_id` 放入 `X-Avatar-Client`。该身份对应自己的会话历史。

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
        "text": "今天过得怎么样？"
    }) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            event = json.loads(line)
            if event["type"] == "text":
                print(event["data"]["text"])
```

事件包含 `turn_start`、`stream_start`、`text`、`audio`、`motion`、`face`、`stream_end`、`turn_end`、`cancelled`、`error`。文本携带逐段表演信息。音频为 base64 编码的 24 kHz 单声道小端 PCM16。`sample_offset` 是累计音频采样数，`sequence` 单调递增；动画以音频采样时钟同步。

`POST /api/turns/{turn_id}/cancel` 取消当前客户端的回复；断开 HTTP 流也会取消。`/ws` 使用同一事件协议，接收 `SpeakRequest` 或 `{"type":"cancel","turn_id":"..."}`。中断状态会保存在导出记录中。

## 会话与主动聊天

| 接口 | 用途 |
| --- | --- |
| `POST /api/conversations` | 为指定角色创建会话，已有空会话时复用 |
| `GET /api/conversations?character_id=ID` | 会话列表，包含 `has_content` |
| `GET /api/conversations/{id}` | 消息、表演、完成状态、主动设置 |
| `GET /api/conversations/{id}/export` | 导出完整 JSON，包含时间戳与中断状态 |
| `PATCH /api/conversations/{id}/initiative` | 设置 `enabled`、`idle_seconds`（10–600）、`cooldown_seconds`（30–3600） |
| `POST /api/conversations/{id}/initiative/check` | 提交 `idle_seconds`、`visible`、`typing`、`recording`、`playing` |

允许主动回复时返回 `topic` 与 `ticket`。以 `source="initiative"`、`initiative_ticket=ticket`、`text=topic` 提交回复；服务端消费一次性票据并使用保存的话题。票据在 45 秒后或上下文改变后失效。客户端发送前应再次确认输入和录音状态。

## 创建角色

`POST /api/creations` 接收：

```json
{"description":"温暖又活泼的成年花店主人", "locale":"zh-CN",
 "image_base64":"...", "presentation":"2d", "voice_candidates":5, "seed":42}
```

`presentation` 为 `2d` 或 `3d`；`locale` 为 `en`、`zh-CN` 或 `ja`，默认 `zh-CN`，用于人设和参考声线。图片为 PNG/JPEG/WebP，最大 10 MB，最短边至少 128 像素。声线候选为 3–8 个。返回 HTTP 202 和持久化任务 ID。

`POST /api/characters/import-live2d?description=...&voice_candidates=5&locale=zh-CN` 接收 `application/zip`。压缩包最大 128 MB，解压后最大 512 MB、4096 个文件。多个模型时使用 `model_entry=path/to/model.model3.json` 选择，详见[角色资源](resources.md)。

| 接口 | 用途 |
| --- | --- |
| `GET /api/studio` | 创建能力与阶段 |
| `GET /api/creations`、`GET /api/creations/{id}` | 状态、进度、结果角色 |
| `POST /api/creations/{id}/cancel`、`.../retry` | 取消或恢复 |
| `GET /api/characters`、`GET /api/characters/{id}` | 角色目录与契约 |
| `PATCH /api/characters/{id}` | 修改 `display_name` 与 `persona` |
| `GET /api/characters/{id}/studio` | 人设、声线、来源 |
| `GET /api/characters/{id}/voice/{candidate}` | 候选 WAV |
| `POST /api/characters/{id}/voice` | 用 `{"candidate":2}` 选择后续回复的声音 |
| `GET /api/characters/{id}/export` | 完整角色 ZIP |
| `POST /api/transcribe` | 0.2–30 秒、16 kHz 单声道 PCM16，字段 `pcm_base64`、`sample_rate` |
| `GET /api/agents` | 智能体角色与模型 |
| `POST /api/agents/character-design` | `description`、`locale` → `CharacterDesign` |
| `POST /api/agents/voice-direction` | `text`、可选 `persona` → `Delivery` |
| `GET /api/services`、`GET /healthz` | 服务就绪状态 |

机器可读契约见 `schemas/`；扩展边界见[架构](architecture.md)。

[← 全部指南](index.md)
