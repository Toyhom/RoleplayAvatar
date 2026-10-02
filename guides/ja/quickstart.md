# クイックスタート

[English](../quickstart.md) · [简体中文](../zh-CN/quickstart.md) · [日本語](quickstart.md)

CPU プレビューでは画面と通信を確認できます。実際の会話には言語モデルと音声サービス、画像からの作成には画像処理と音声設計モデルを追加します。AI に作業を依頼する場合は[セットアップ手順](ai-setup.md)をコピーしてください。

## 1. 画面を起動する

Python 3.11 と Node.js 18+ を用意し、リポジトリのルートで実行します。

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,download]'
npm ci
npm run build
AVATAR_MODE=replay .venv/bin/python -m uvicorn roleplay_avatar.app:create_app --factory --port 18080
```

http://localhost:18080 を開き、キャラクターを選んで送信します。このモードは固定の会話と診断用音声を使用します。実モデルへ切り替える前に Ctrl+C で停止します。

## 2. モデルを選ぶ

`--vram-gib` には GPU 1 枚あたりのメモリを指定します。

```bash
.venv/bin/avatar models recommend --vram-gib 24 --gpus 1
.venv/bin/avatar models download compact --model-root /path/to/models --dry-run
```

`--dry-run` を外すとダウンロードします。中国国内向けミラーは `--mirror`、任意のミラーは `--endpoint URL` で指定できます。画像作成用のモデルを含めるには `--creation` を追加します。

[モデルと設定](models.md)で API 接続やプリセットを選び、[詳細なインストール手順](setup.md)でモデル環境とサービスを準備します。`AVATAR_*_URL` を設定し、`bash scripts/serve.sh` でアプリを起動します。

## 3. キャラクターと会話する

2D または 3D を選び、画像と短い説明をアップロードします。完成済み Live2D は ZIP でインポートできます。作成時に設定を補完し、3～8 個の音声候補とアニメーション設定を生成します。

キャラクターごとに会話を管理し、JSON で書き出せます。マイク入力には localhost または HTTPS とブラウザの録音許可が必要です。音声の中断や、会話ごとの自発的な発話も利用できます。

| 症状 | 確認する項目 |
| --- | --- |
| モデルが見つからない | `.local.env` を読み込んで `avatar doctor` を実行し、ダウンロード先を確認します。 |
| サービスが利用できない | サービスログ、`/healthz`、`AVATAR_*_URL` を確認します。 |
| API が 401 を返す | 対応するキーの環境変数を確認します。 |
| GPU メモリが足りない | 小さいプリセットを選ぶか、作成処理と会話サービスを別の GPU に割り当てます。 |

[← ガイド一覧](index.md)
