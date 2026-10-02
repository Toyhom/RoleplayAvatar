# Roleplay Avatar · 鏡界

本フレームワークはロールプレイ対話の研究・テスト専用です。現行バージョンはまだ粗い段階です。

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

キャラクターに姿、声、そして会話を。

画像と短い説明から、会話できる 2D キャラクターを作成します。完成済みの Live2D モデルを読み込み、声を選んでマイクで話しかけることもできます。返答には表情、動作、話し方が含まれ、キャラクターごとに独立した会話履歴を保存し、JSON で書き出せます。自発的な会話を有効にすると、制御エージェントが状況に応じて話しかけるタイミングを判断します。

ロールプレイ、キャラクター設計、音声、アニメーションの各モデルを交換できます。ローカルモデルと外部 API を個別に選択し、組み合わせて運用できます。ヘッドレス API からも同じ作成・会話フローを利用でき、アプリ開発とロールプレイ研究に活用できます。

https://github.com/user-attachments/assets/47e32f4e-94e6-4a0f-978d-8a36a8303a89

**30 秒の機能紹介：** [English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

[ガイド一覧](guides/ja/index.md)

## はじめに

| 目的 | ガイド |
| --- | --- |
| モデルを設定して会話を始める | [クイックスタート](guides/ja/quickstart.md) |
| Codex / Claude Code にセットアップを依頼する | [コピー用の手順](guides/ja/ai-setup.md) |
| ハードウェアに合わせてモデルを選ぶ | [モデル・プリセット・ダウンロード](guides/ja/models.md) |
| DeepSeek、Qwen、OpenAI、Claude に接続する | [プロバイダーと設定](guides/ja/providers.md) |
| ローカル環境を構築する | [詳細なインストール手順](guides/ja/setup.md) |
| ローカル推論の高速化と VRAM 調整 | [性能設定](guides/ja/performance.md) |
| アプリと連携する | [API](guides/ja/api.md) · [構成](guides/ja/architecture.md) |
| 独自モデルやプロンプトを評価する | [研究ガイド](guides/ja/research.md) |

## 作成と会話

1. 作成時に **2D** または **3D** を選び、画像をアップロードします。2D では Live2D ZIP も利用できます。
2. 性格と声を説明し、音声候補を試聴して選びます。
3. テキストまたはマイクで話しかけます。返答の表情と動作がキャラクターに反映されます。
4. 会話に内容が入ったら新しい会話を開始できます。履歴全体を JSON で保存できます。

公式サンプルの Haru、Hiyori、RobotExpressive とインポート仕様は[リソースガイド](guides/ja/resources.md)、音声の調整は[音声ガイド](guides/ja/voice.md)で説明しています。

## モデルの選択

ハードウェアプリセットは単一 GPU 構成から大規模な複数 GPU 構成まで対応しています。カタログには各モデルシリーズのサイズ別モデルと、バージョンを固定したダウンロードが含まれます。

```bash
.venv/bin/avatar models recommend --vram-gib 24 --gpus 1
.venv/bin/avatar models download compact --mirror --model-root /path/to/models
.venv/bin/avatar models configure compact --model-root /path/to/models
```

エージェントごとに OpenAI Chat Completions、OpenAI Responses、Anthropic Messages、フレームワーク付属のローカルプロトコルを設定できます。プロンプト、生成パラメーター、モデルのパスはそれぞれ独立して設定します。

## ライセンス

独自のフレームワークコードは [MIT](LICENSE) です。モデルとリソースの出典・ライセンスは [NOTICE](NOTICE.md) に記載しています。
