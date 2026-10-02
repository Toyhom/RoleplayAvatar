# クイックスタート

[English](../quickstart.md) · [简体中文](../zh-CN/quickstart.md) · [日本語](quickstart.md)

ローカルモデルまたは外部 API を選んで会話を始めます。音声での対話には音声サービス、画像からのキャラクター作成には画像処理と音声設計モデルを設定します。AI に作業を依頼する場合は[セットアップ手順](ai-setup.md)をコピーしてください。

## 1. アプリをインストールする

Python 3.11 と Node.js 18+ を用意し、リポジトリのルートで実行します。

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,download]'
npm ci
npm run build
```

## 2. モデルを設定してサービスを起動する

`--vram-gib` には GPU 1 枚あたりのメモリを指定します。

```bash
.venv/bin/avatar models recommend --vram-gib 24 --gpus 1
.venv/bin/avatar models download compact --model-root /path/to/models --dry-run
```

`--dry-run` を外すとダウンロードします。中国国内向けミラーは `--mirror`、任意のミラーは `--endpoint URL` で指定できます。画像作成用のモデルを含めるには `--creation` を追加します。

ローカル会話の推論エンジンとメモリ予算は[性能ガイド](performance.md)で設定します。

[モデルと設定](models.md)で API 接続やプリセットを選び、[詳細なインストール手順](setup.md)でモデル環境とサービスを準備します。`AVATAR_*_URL` を設定し、`bash scripts/serve.sh` でアプリを起動し、**http://localhost:18080** を開きます。

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
