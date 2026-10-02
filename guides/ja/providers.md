# プロバイダーと設定

[English](../providers.md) · [简体中文](../zh-CN/providers.md) · [日本語](providers.md)

各エージェントにプロバイダー、モデル、生成設定、プロンプトを指定できます。一つのモデルで全役割を担当する構成と、役を演じるモデルと制御モデルを分ける構成を選べます。

## プロバイダーに接続する

`configs/models.local.json` を作成します。

```json
{"agents":{"default":{"provider":"qwen","model":"qwen-plus","require_key":true,
                        "extra_body":{"enable_thinking":false}}}}
```

環境または私用の `.local.env` に設定します。

```bash
export AVATAR_MODELS_CONFIG="$PWD/configs/models.local.json"
export DASHSCOPE_API_KEY='your-key'
```

Web プロセスを再起動すると反映されます。作成ワーカーは新しいタスクの開始時に読み込みます。

| provider | プロトコル | 既定 URL | キーの環境変数 |
| --- | --- | --- | --- |
| `deepseek` | OpenAI Chat Completions | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |
| `qwen` | OpenAI Chat Completions | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` |
| `openai` | OpenAI Chat Completions | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| `anthropic` / `claude` | Anthropic Messages | `https://api.anthropic.com/v1` | `ANTHROPIC_API_KEY` |
| `openai-compatible` | OpenAI Chat Completions | `http://127.0.0.1:8000/v1` | `AVATAR_LLM_API_KEY` |
| `local` | `/chat` NDJSON | `http://127.0.0.1:18110` | 任意の `AVATAR_LLM_API_KEY` |

`model` はアカウントで使用できる ID を指定します。`url` で地域別エンドポイント、プロキシ、vLLM、SGLang、llama.cpp を選択します。認証のないローカル接続では `require_key:false` とします。

## モジュールごとのルーティング

```json
{
  "agents": {
    "default":{"provider":"qwen","model":"qwen-plus"},
    "roleplay":{"provider":"openai-compatible","url":"http://localhost:8000/v1",
                "model":"my-roleplay-checkpoint","output_mode":"actor_director","require_key":false},
    "performance_director":{"generation":{"temperature":0.2}},
    "initiative":{"provider":"deepseek","model":"deepseek-chat"},
    "character_design":{"provider":"anthropic","model":"YOUR_CLAUDE_MODEL_ID"},
    "voice_direction":{"provider":"openai","model":"YOUR_OPENAI_MODEL_ID"}
  }
}
```

`agents.<role>` が `agents.default` を上書きします。プロバイダーを変えると、継承した URL、キー変数、モデル、固有拡張はリセットされるため、モデル ID を明示します。同じプロバイダーの場合、`generation` と `extra_body` の項目をマージします。

`performance` は演技 JSON を直接生成します。`actor_director` は自然な返答を生成した後、`performance_director` が台詞・表情・動作を抽出します。[研究ガイド](research.md)に詳細があります。

## 生成とプロトコルのオプション

`generation` は `temperature`、`top_p`、`max_tokens`、`seed` とプロバイダー対応項目を受け取ります。設定値は呼び出し時の既定値より優先されます。`null` を指定すると送信を省略できます。

`extra_body` は `enable_thinking` など固有拡張用です。メッセージ、モデル、ルーティングはゲートウェイが管理します。推論過程は発話テキストから分離します。

OpenAI Responses の例：

```json
{"provider":"openai", "backend":"openai-responses", "model":"YOUR_MODEL_ID",
 "generation":{"temperature":null, "max_tokens":1400}}
```

`max_tokens` を `max_output_tokens` に変換します。Chat Completions の新しい上限フィールドは `max_tokens_field:"max_completion_tokens"` で指定します。Anthropic はネイティブの `/messages`、`x-api-key`、テキストイベントを使います。`timeout_s` でタイムアウトを変更できます。

組織独自のプロバイダーも登録できます。

```json
{"providers":{"lab":{"backend":"openai","url":"https://models.example.org/v1",
                        "api_key_env":"LAB_MODEL_KEY"}},
 "agents":{"default":{"provider":"lab","model":"research-model"}}}
```

## 画像理解を API で行う

```json
{"models":{"vision":{"adapter":"api"}},
 "agents":{"vision":{"provider":"qwen","model":"qwen-vl-plus"}}}
```

作成ワーカーが画像と設計プロンプトを送信します。OpenAI 互換と Anthropic の画像メッセージに対応します。画像生成と音声にはそれぞれのアダプターを使います。[構成](architecture.md)を参照してください。

## プロンプトファイル

`prompts` は文字列、または JSON 設定からの相対パスを受け取ります。

```json
{"prompts":{"actor":{"file":"../prompts/local/actor.txt"},
            "initiative":"この会話に短い続きの発話が適しているか判断してください。"}}
```

既定のファイルは `src/roleplay_avatar/prompt_templates/` にあります。名前は `roleplay`、`actor`、`performance`、`performance_director`、`initiative`、`character_design`、`voice_direction`、`vision`、`image_2d`、`image_3d`。視覚テンプレートは `{description}`、画像生成は `{appearance}` を使えます。キャラクター固有の設定はパッケージに保持します。

設定例：[混合プロバイダー](../../configs/providers.example.json)、[研究](../../configs/research.example.json)、[モデルパス](../../configs/models.example.json)。

[← ガイド一覧](index.md)
