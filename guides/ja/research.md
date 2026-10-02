# ロールプレイ研究と独自手法

[English](../research.md) · [简体中文](../zh-CN/research.md) · [日本語](research.md)

音声、描画、会話保存、書き出しを維持しながら、役を演じるモデル、プロンプト、生成方針を個別に差し替えられます。`configs/research.example.json` から始め、二つの出力モードを選択します。

## 演技を直接生成する

`agents.roleplay.output_mode` を `performance` にします。モデルは改行区切りの JSON セグメントを出力します。

```json
{"text":"好きな花を覚えていてくれたんだ！", "emotion":"happy", "intensity":0.5,
 "action_intent":"acknowledge", "actions":[{"name":"nod","start_s":0,"duration_s":1.6,"strength":0.5}],
 "delivery":{"tone":"warm","pace":"natural","pause_after_ms":260}}
```

アプリは段階的に解析します。`Segment` 契約を保って `prompts.performance` を変更できます。

## 役を演じるモデルと演出エージェント

`output_mode: "actor_director"` では、モデルが自然な会話とト書きを生成し、`performance_director` が発話可能なセグメントに変換します。心内描写を音声から分離し、動作を対応するジェスチャーに割り当てます。専用モデルの出力形式を維持したい場合に適しています。返答全体を受け取ってから演出を開始するため、直接生成モードは最初の応答を早く出せます。

役を演じるモデルは設定と現在の会話を受け取ります。過去の演技記録は台詞へ戻して文脈に含めます。`prompts.actor`、`prompts.roleplay`、キャラクター設定は個別に変更でき、演出側にも専用のプロンプトと生成設定があります。既定ではユーザーの指定言語、またはメッセージの言語に合わせます。元の出力言語を保持する研究では `prompts.performance_director` を差し替えるか、`ModelGateway` で直接評価します。

既定のプロンプトは簡潔な台詞とト書きを求めます。長い叙述では `prompts.actor` と `agents.roleplay.generation.max_tokens` を合わせて変更します。

## モデル、プロンプト、推論方針

| 設定 | 用途 |
| --- | --- |
| `models.<role>.path` | ローカルのチェックポイント |
| `agents.<role>` | エンドポイント、プロトコル、モデル ID |
| `agents.<role>.generation` | サンプリングと長さ。ローカルでは temperature、top_p、repetition_penalty、seed、stop に対応 |
| `models.<role>.chat_template` | ローカルの Jinja テンプレート |
| `models.<role>.template_kwargs` | 思考モードなどのテンプレートオプション |
| `models.<role>.eos_token_id` | 独自形式の終了 token ID またはリスト |
| `prompts.<name>` | 文字列または UTF-8 ファイル |

ローダーはチェックポイントと tokenizer 両方の終了 token を扱います。`AVATAR_MODELS_CONFIG` で設定を選び、プロンプトファイルは設定からの相対パスで解決します。条件を変えたら対象プロセスを再起動し、新しい会話を作成します。

## 同じインターフェースで評価する

キャラクターと条件ごとに独立した会話を作り、HTTP NDJSON でストリームを受け取り、完全な JSON 履歴を保存します。テキスト、演技メタデータ、時刻、完了・中断状態が含まれます。モデルの出力だけを必要とする場合は、ゲートウェイを直接呼び出せます。

```python
import asyncio
from roleplay_avatar.agents import ModelGateway

async def evaluate():
    output = []
    async for token in ModelGateway("roleplay").stream(
        "あなたは辛抱強い灯台守です。",
        [{"role":"user", "content":"嵐が来ます。どうすればいい？"}],
        max_tokens=500, temperature=0.7,
    ):
        output.append(token)
    return "".join(output)

print(asyncio.run(evaluate()))
```

比較では設定、参照音声、入力、描画設定を揃え、モデルのリビジョン、プロンプト、生成設定を記録します。応答時間には役のモデル、任意の演出モデル、最初の音声ブロックが含まれます。応答性の評価では各段階を分けて測ります。

## 手法を拡張する

`ModelGateway` の前段に検索、記憶、計画、複数キャラクターの調整を実装できます。既存プロトコルのモデルサービスを置き換えることもできます。会話の所有とターンの中断は編成層が管理します。境界は[構成](architecture.md)、呼び出しと書き出しは [API](api.md)を参照してください。

[← ガイド一覧](index.md)
