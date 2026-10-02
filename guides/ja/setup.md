# インストールとデプロイ

[English](../setup.md) · [简体中文](../zh-CN/setup.md) · [日本語](setup.md)

CPU の Web プロセスが独立した推論サービスを調整します。各サービスに環境と GPU を割り当てます。通常は会話、音声、認識、音声表情と、キャラクター作成ワーカーを起動します。

## 1. アプリの準備

Python 3.11、Node.js 18+、FFmpeg、SoX、libsndfile を用意します。[クイックスタート](quickstart.md)で Web 環境と UI を構築します。`.local.env.example` を `.local.env` にコピーして設定します。

```bash
AVATAR_ENV_PREFIX=/absolute/path/to/project/.venv
AVATAR_MODEL_ROOT=/absolute/path/to/models
AVATAR_MODELS_CONFIG=/absolute/path/to/project/configs/models.local.json
AVATAR_PORT=18080
```

スクリプトは `scripts/common.sh` から環境を読み込みます。実際のパスを入力し、確認します。

```bash
source scripts/common.sh
"$PYTHON" -m roleplay_avatar.cli doctor
```

分割重みの索引、Diffusers コンポーネント、取得記録のファイルサイズを確認します。不完全な重みは対応するダウンロードコマンドで補完します。

## 2. モデル環境

固定リビジョンの実装を取得します。

```bash
source scripts/common.sh
"$PYTHON" scripts/fetch_upstreams.py --only cosyvoice qwen3_tts
git -C third_party/cosyvoice submodule update --init --recursive
```

GPU 用の例は Python 3.10、Web と CPU 顔検出は 3.11 です。例えば `conda create -p /srv/envs/avatar-base310 python=3.10` で基礎環境を作り、その Python の絶対パスと新しい保存先を指定します。

```bash
bash scripts/install_model_env.sh vision /absolute/python3.10 /srv/envs/avatar-vision
bash scripts/install_model_env.sh qwen /absolute/python3.10 /srv/envs/avatar-qwen
bash scripts/install_model_env.sh cosyvoice /absolute/python3.10 /srv/envs/avatar-cosyvoice
bash scripts/install_model_env.sh face /absolute/python3.11 /srv/envs/avatar-face
bash scripts/install_model_env.sh portrait /absolute/python3.11 /srv/envs/avatar-portrait
bash scripts/install_model_env.sh audio2face /absolute/python3.10 /srv/envs/avatar-audio2face
```

vision は LLM、視覚、画像生成、Whisper に使います。CosyVoice は独立した Torch 2.3.1、vision/Qwen は Torch 2.8 です。顔検出は MediaPipe、立ち絵は rembg/ONNXRuntime を使います。`.local.env` に `AVATAR_LLM_PYTHON`、`AVATAR_VISION_PYTHON`、`AVATAR_QWEN_PYTHON`、`AVATAR_TTS_PYTHON`、`AVATAR_FACE_PYTHON`、`AVATAR_PORTRAIT_PYTHON`、`AVATAR_ASR_PYTHON`、`AVATAR_AUDIO_FACE_PYTHON` を指定します。

Live2D は設定設計と VoiceDesign、画像作成はさらに視覚、画像、顔、立ち絵環境を使います。任意の 3D は asset 環境と `configs/upstreams.lock.json` の AniGen、DSINE、幾何処理依存を追加します。

## 3. モデルと資源の取得

```bash
.venv/bin/avatar models download balanced --creation --mirror --model-root /srv/models
.venv/bin/avatar models configure balanced --creation --model-root /srv/models
source scripts/common.sh
"$PYTHON" scripts/download_face_model.py
"$PYTHON" scripts/download_audio_face_model.py
"$PYTHON" scripts/download_segmentation_model.py
"$PYTHON" scripts/fetch_demo_characters.py
```

カタログが Hugging Face スナップショットを取得し、補助スクリプトが MediaPipe、UniTalker を取得します。BiRefNet は `$AVATAR_MODEL_ROOT/rembg/birefnet-general.onnx` に保存し、`AVATAR_SEGMENTATION_MODEL_PATH` で既存ファイルを指定できます。声とサンプルの導入は[リソース](resources.md)にあります。

## 4. 推論サービスの起動

以下を GPU ランナーの実行内容として使います。共有 GPUQ では所有者アカウントで `gpuq submit --node auto --gpus N -- ...` に送信します。[モデル表](models.md)を基に、同時実行する制御サービスも含めて GPU 数を選びます。パスは実際のモデルディレクトリに変更します。

```bash
"$AVATAR_LLM_PYTHON" services/llm_service.py --model /srv/models/my-chat-checkpoint --port 18110
"$AVATAR_TTS_PYTHON" services/speech_service.py --model /srv/models/my-cosyvoice3 --port 18120
"$AVATAR_ASR_PYTHON" services/whisper_service.py --model /srv/models/my-whisper --port 18140 --language auto
"$AVATAR_AUDIO_FACE_PYTHON" services/audio_face_service.py --model /srv/models/my-unitalker.onnx --port 18130
```

外部モデルは[プロバイダー](providers.md)を設定します。代替音声の例：

```bash
"$AVATAR_QWEN_PYTHON" services/family_speech_service.py --backend qwen-base --model /srv/models/qwen-tts-base --port 18120
```

`qwen-custom` は `--speaker`、`cosyvoice-auto` は互換ディレクトリの自動選択に対応します。これらは一文を合成してから送信します。既定の CosyVoice3 は生成中に送信します。

Web からの接続先を設定します。

```bash
AVATAR_LLM_URL=http://127.0.0.1:18110
AVATAR_TTS_URL=http://127.0.0.1:18120
AVATAR_ASR_URL=http://127.0.0.1:18140
AVATAR_AUDIO_FACE_URL=http://127.0.0.1:18130
AVATAR_CREATION_RUNNER=local
```

GPUQ では `AVATAR_CREATION_RUNNER=gpuq` を使います。`AVATAR_CREATION_GPUS` は順次実行する作成ワーカーの GPU 数で、既定は一枚です。`bash scripts/serve.sh` を実行し、http://localhost:18080 と `/api/services` を確認します。上部で英語・中国語・日本語を選択できます。作成言語は画面から伝わり、ASR は `auto` を推奨します。

モデル設定は対象プロセスの再起動で反映されます。`scripts/demo.py` は設定済みの三ノード GPUQ 管理用、各サービスコマンドと Web 起動は可搬性のある入口です。

## 5. API のみで使う

`AVATAR_HEADLESS=1` で作成、会話、音声ストリーム、書き起こし、書き出しを提供します。仕様は `/docs` と `/openapi.json`。`AVATAR_API_KEY` で認証を有効にします。参照実装は単一 Uvicorn worker とファイル保存です。アプリ側の認証や DB を [API](api.md) に接続できます。

## データと更新

`characters/` はパッケージと声の選択、`outputs/creations/` は作成ジョブ、`outputs/conversations/` は会話履歴です。ZIP は八ファイル契約、参照先、出典を保持します。

復元後は `avatar validate PATH --require-assets` を実行します。`scripts/split_character_modes.py` は旧形式の 2D/3D 共存パッケージを別 ID に分割し、`outputs/migrations/` にメタデータを退避します。

## 確認

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
npm run build
node --test tests/*.test.mjs
python scripts/check_docs.py
```

`check_studio.py`、`check_demo_library.py`、`check_conversations.py`、`check_microphone.py`、`check_localization.py` で作成、描画、文脈、マイク、多言語 UI を確認できます。結果は `outputs/` に保存します。

## 一つの GPU 割り当てを共有する

`configs/services.example.json` を `configs/services.local.json` にコピーし、サービスと Python を指定します。`.local.env` を読み込み、`services/service_group.py --config configs/services.local.json` を `scripts/gpu_worker.sh` 経由で一つの GPUQ タスクとして送信します。子は同じ CUDA 割り当てを継承し、別のポートとログを使います。

大きな構成には [services.showcase.example.json](../../configs/services.showcase.example.json) があります。制御、音声、認識、表情を一枚の 80 GB GPU に、70B の役モデルを二枚の 80 GB GPU、ポート 18112 に配置します。`models.roleplay.device_map=balanced` で分散し、作成は別途割り当てます。子が終了するとグループも停止し、失敗を通知します。

三ノード起動器は `AVATAR_SERVICE_GROUP_CONFIG` に対応します。制御モデルが役も担当する場合は `AVATAR_LLM_IN_GROUP=1` を指定します。`python scripts/demo.py start --replace-changed` はコマンド、パス、GPU 数、設定ハッシュを比較して変更したサービスを再配置します。

SSH はノード別名、または `AVATAR_SSH_SYSTEM2_HOST`、`AVATAR_SSH_SYSTEM2_PORT`、`AVATAR_SSH_SYSTEM2_HOST_KEY_ALIAS`（system3 も同様）で接続します。host-key alias は既存の信頼済み鍵を指します。監視プロセスはサービス移動時に古い逆方向転送を解放します。

[← ガイド一覧](index.md)
