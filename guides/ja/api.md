# バックエンド API

[English](../api.md) · [简体中文](../zh-CN/api.md) · [日本語](api.md)

`AVATAR_HEADLESS=1` で API のみを提供します。ブラウザーも同じ API を利用します。対話式仕様は `/docs`、OpenAPI は `/openapi.json` です。`AVATAR_API_KEY` を設定した場合、`Authorization: Bearer KEY` を送信します。

## 会話の作成とストリーミング

`POST /api/conversations/client` でクライアントを作成し、返された Cookie を保持するか、`client_id` を `X-Avatar-Client` に指定します。この識別子でクライアント自身の会話履歴にアクセスします。

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
        "text": "今日はどんな一日だった？"
    }) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            event = json.loads(line)
            if event["type"] == "text":
                print(event["data"]["text"])
```

イベントは `turn_start`、`stream_start`、`text`、`audio`、`motion`、`face`、`stream_end`、`turn_end`、`cancelled`、`error` です。テキストには各発話区間の演技情報を含みます。音声は base64 の 24 kHz・モノラル・リトルエンディアン PCM16 です。`sample_offset` は累積サンプル数、`sequence` は単調増加する番号です。描画は音声のサンプル時刻に同期します。

`POST /api/turns/{turn_id}/cancel` でクライアント自身のターンを中断できます。HTTP ストリームの切断でも中断します。`/ws` は同じイベント仕様を使い、`SpeakRequest` または `{"type":"cancel","turn_id":"..."}` を受け取ります。中断状態は履歴に残ります。

## 会話と自発的な発話

| API | 用途 |
| --- | --- |
| `POST /api/conversations` | 指定キャラクターの会話を作成。空の会話があれば再利用 |
| `GET /api/conversations?character_id=ID` | `has_content` を含む会話一覧 |
| `GET /api/conversations/{id}` | メッセージ、演技、状態、自発的発話の設定 |
| `GET /api/conversations/{id}/export` | 時刻と完了・中断状態を含む JSON |
| `PATCH /api/conversations/{id}/initiative` | `enabled`、`idle_seconds`（10–600）、`cooldown_seconds`（30–3600） |
| `POST /api/conversations/{id}/initiative/check` | `idle_seconds`、`visible`、`typing`、`recording`、`playing` を送信 |

発話を許可する判定では `topic` と `ticket` が返ります。`source="initiative"`、`initiative_ticket=ticket`、`text=topic` でターンを送信します。サーバーは一度限りのチケットを消費し、保存された話題を使います。45 秒経過または文脈の変更で失効します。送信直前にも入力・録音状態を確認してください。

## キャラクター作成

`POST /api/creations` の入力例：

```json
{"description":"温かく遊び心のある大人の花屋", "locale":"ja",
 "image_base64":"...", "presentation":"2d", "voice_candidates":5, "seed":42}
```

`presentation` は `2d` または `3d`。`locale` は `en`、`zh-CN`、`ja` で、既定値は `zh-CN` です。設定文と参照音声の言語に使います。PNG/JPEG/WebP、最大 10 MB、短辺 128 ピクセル以上に対応します。声の候補は 3–8 種類です。HTTP 202 と永続的なジョブ ID を返します。

`POST /api/characters/import-live2d?description=...&voice_candidates=5&locale=ja` に `application/zip` を送信します。圧縮後 128 MB、展開後 512 MB、4096 ファイルが上限です。複数モデルを含む場合は `model_entry=path/to/model.model3.json` を指定します。[リソース](resources.md)も参照してください。

| API | 用途 |
| --- | --- |
| `GET /api/studio` | 作成機能の状態と処理段階 |
| `GET /api/creations`、`GET /api/creations/{id}` | ジョブ状態、進捗、作成したキャラクター |
| `POST /api/creations/{id}/cancel`、`.../retry` | 中止または再開 |
| `GET /api/characters`、`GET /api/characters/{id}` | キャラクター一覧と契約 |
| `PATCH /api/characters/{id}` | `display_name`、`persona` の更新 |
| `GET /api/characters/{id}/studio` | 設定、声、出典 |
| `GET /api/characters/{id}/voice/{candidate}` | 候補の WAV |
| `POST /api/characters/{id}/voice` | `{"candidate":2}` で次の返信から使う声を選択 |
| `GET /api/characters/{id}/export` | キャラクター全体の ZIP |
| `POST /api/transcribe` | 0.2–30 秒の 16 kHz モノラル PCM16。`pcm_base64`、`sample_rate` |
| `GET /api/agents` | エージェントの役割とモデル |
| `POST /api/agents/character-design` | `description`、`locale` → `CharacterDesign` |
| `POST /api/agents/voice-direction` | `text`、任意の `persona` → `Delivery` |
| `GET /api/services`、`GET /healthz` | サービスの稼働状態 |

機械可読の契約は `schemas/`、拡張点は[構成](architecture.md)にあります。

[← ガイド一覧](index.md)
