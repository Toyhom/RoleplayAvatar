# クイックスタート

[English](../quickstart.md) · [简体中文](../zh-CN/quickstart.md) · [日本語](quickstart.md)

次の四つの手順でアプリをインストールし、モデルを接続して会話を始めます。Codex や Claude Code に作業を依頼する場合は、[AI 向けセットアップ手順](ai-setup.md)をコピーしてください。

## 1. アプリをインストールする

Git、Python 3.11、Node.js 18+ を用意します。音声とキャラクター作成には、[インストールガイド](setup.md)に従って FFmpeg、SoX、libsndfile も用意します。

リポジトリをクローンし、アプリをインストールして画面をビルドします。既にクローン済みなら、そのルートディレクトリで最初の二つのコマンドを省略して実行します。

```bash
git clone https://github.com/Toyhom/RoleplayAvatar.git
cd RoleplayAvatar
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[download]'
npm ci
npm run build
```

## 2. モデルを選んで設定する

| 会話の方式 | 用意するもの | 設定ガイド |
| --- | --- | --- |
| 外部 API | プロバイダーのアカウント、API キー、モデル名 | [プロバイダー](providers.md) |
| ローカルモデル | モデルの重みと必要な GPU メモリ | [モデルとプリセット](models.md) · [推論性能](performance.md) |

音声合成、マイクの文字起こし、キャラクター作成には、それぞれのモデルサービスを使います。[インストールガイド](setup.md)で必要な機能を設定します。会話に外部 API を使い、その他のサービスをローカルで動かすこともできます。

### 外部 API を使う

[プロバイダーガイド](providers.md)に従い、`configs/models.local.json` に各エージェントの接続先、モデル名、API キーの環境変数名を設定し、手順 3 に進みます。

### ローカルモデルを使う

まずハードウェアに合う推奨構成を確認します。`--vram-gib` は GPU 一枚あたりのメモリです。手元の構成に合わせて数値を変更してください。

```bash
.venv/bin/avatar models recommend --vram-gib 24 --gpus 1
```

次は `compact` プリセットのダウンロードと設定例です。`compact` は選んだプリセットに、`/path/to/models` は保存先の絶対パスに置き換えます。

```bash
.venv/bin/avatar models download compact --mirror --model-root /path/to/models
.venv/bin/avatar models configure compact --model-root /path/to/models
```

- `--mirror` は [hf-mirror.com](https://hf-mirror.com) を使います。省略すると Hugging Face を使い、別のミラーは `--endpoint URL` で指定できます。
- 取得前に一覧を確認するには、ダウンロードコマンドに `--dry-run` を追加します。
- 画像からの作成、または音声設計を伴う Live2D インポートには、ダウンロードと設定の両コマンドに `--creation` を追加します。
- 設定コマンドは `configs/models.local.json` を作成します。既存の設定は直接編集するか、`--output` で別のファイルを指定します。

## 3. モデルサービスとアプリを起動する

初回のインストール時にデプロイ設定を作成します。

```bash
cp .local.env.example .local.env
```

`.local.env` にアプリの環境、モデルの保存先、`configs/models.local.json` の絶対パス、サービスの Python 実行ファイル、`AVATAR_*_URL` の接続先を記入します。次回以降もこのファイルを使います。

[インストールガイド](setup.md)に従って選んだモデルの環境を準備し、サービスを起動します。ローカル会話の推論エンジンとメモリ予算は[性能ガイド](performance.md)で設定します。

設定を確認し、アプリを起動します。

```bash
source scripts/common.sh
"$PYTHON" -m roleplay_avatar.cli doctor
bash scripts/serve.sh
```

[http://localhost:18080](http://localhost:18080) を開きます。[/api/services](http://localhost:18080/api/services) で設定したサービスの準備状態を確認します。使用中はサービスの端末を開いたままにします。各端末で Ctrl+C を押すと、対応するフォアグラウンドプロセスを停止できます。

## 4. キャラクターを作成して会話する

1. **2D** または **3D** を選び、画像と短い説明をアップロードします。2D では完成済み Live2D ZIP もインポートできます。
2. 生成された音声候補を試聴して選びます。既存サンプルの導入方法は[リソースガイド](resources.md)にあります。
3. テキストまたはマイクで話しかけます。マイクには localhost または HTTPS でのアクセスと、ブラウザの録音許可が必要です。
4. 音声の中断、JSON の書き出し、自発的な会話を利用できます。会話はキャラクターごとに独立し、現在の会話に実質的な内容が入ると新しい会話を作成できます。

## よくある問題

| 症状 | 確認する項目 |
| --- | --- |
| モデルが見つからない | `source scripts/common.sh` で `.local.env` を読み込み、`"$PYTHON" -m roleplay_avatar.cli doctor` を実行して取得先と設定を比較します。 |
| サービスが利用できない | 対応するログ、`/healthz`、`AVATAR_*_URL` を確認します。 |
| API が 401 を返す | そのエージェントに指定したキーの環境変数を確認します。 |
| GPU メモリが足りない | 小さいプリセットを選ぶか、サービスを別々の GPU に割り当てます。キャラクター作成は分けて実行できます。 |
| マイクが使えない | localhost または HTTPS で開き、ブラウザの録音許可を確認します。 |
| ダウンロードに認証が必要 | モデルリポジトリの利用申請を済ませ、`--token-env HF_TOKEN` で認証情報を指定します。 |

[← ガイド一覧](index.md)
