# モデル、ハードウェア、ダウンロード

[English](../models.md) · [简体中文](../zh-CN/models.md) · [日本語](models.md)

vLLM、SGLang、llama.cpp とモジュールごとのメモリ設定は[ローカル推論と性能設定](performance.md)を参照してください。

パスがチェックポイントを選び、アダプターが推論を実装し、エージェントがローカル・外部接続を選びます。[モデルカタログ](../../src/roleplay_avatar/data/models.json)にはリポジトリ ID、固定リビジョン、アダプター、ライセンス、概算 VRAM を記録しています。

## ハードウェア別プリセット

会話、音声、認識の同時実行を想定しています。キャラクター作成は別の処理で、段階ごとにモデルを読み込みます。

| プリセット | 推奨ハードウェア | 会話 | 音声認識 |
| --- | --- | --- | --- |
| API | 小型 GPU または外部音声サービス | 選択するプロバイダー | ローカル/外部 ASR |
| `compact` | 1 × 24 GB | Qwen3-4B | Whisper-small |
| `balanced` | 1 × 40–48 GB | Qwen3-8B | Whisper-large-v3-turbo |
| `quality` | 2 × 80 GB | Qwen3-32B | Whisper-large-v3 |
| `showcase` | 3 × 80 GB | CoSER-70B + Qwen3-8B 制御 | Whisper-large-v3-turbo |

ローカルの四種類は CosyVoice3 を使います。最大構成は役のモデルを二枚に分散し、他のサービスを別に配置します。概算には文脈と活性値の余裕を含み、長さ、解像度、バッチ、精度で変わります。

```bash
avatar models list
avatar models recommend --vram-gib 48 --gpus 1
avatar models download balanced --model-root /srv/models --dry-run
avatar models download balanced --model-root /srv/models --mirror
avatar models configure balanced --model-root /srv/models --output configs/models.local.json
```

`--vram-gib` は GPU 一枚あたりの容量です。configure は新規ファイルを作ります。`AVATAR_MODELS_CONFIG` に絶対パスを指定し、対象サービスを再起動します。環境と URL は[インストール](setup.md)を参照してください。

## ミラーと固定リビジョン

`--mirror` は `https://hf-mirror.com`、`--endpoint URL` は任意の Hugging Face 互換サイトを選びます。commit を固定し、再開可能なダウンロード、文書の保持、LFS SHA256 検証を行います。`.avatar-download.json` に取得情報を記録します。

```bash
avatar models download qwen3-8b --mirror --model-root /srv/models
avatar models download qwen3-vl-32b --mirror --model-root /srv/models
```

`--creation` を加えると画像理解、画像生成、声の設計を含めます。quality/showcase は Qwen3-VL-32B と Qwen-Image-Edit-2511 を選びます。後者は `AVATAR_IMAGE_BACKEND=qwen_image` で使用し、口の参考画像は FLUX を使います。

アクセス制限のあるリポジトリは上流の利用手続きを完了し、`--token-env HF_TOKEN` で資格情報を選びます。選択した接続先にその資格情報を送信します。同じコマンドで再開できます。ダウンロード機能は `python -m pip install -e '.[download]'` で導入します。`scripts/download_snapshot.py` はリポジトリ、リビジョン、ルートを受け取る分割ダウンロード用で、`HF_ENDPOINT` に従います。

## モジュールと系列

| モジュール | 対応系列 | アダプター |
| --- | --- | --- |
| ロールプレイ・テキスト | Qwen3 dense/MoE、CoSER Llama 3.1、互換 causal-LM | `llm_service.py`、AutoModelForCausalLM、独自テンプレート、複数 GPU、任意の int4/int8 |
| 外部エージェント | DeepSeek、Qwen、OpenAI、Claude、互換サーバー | Chat Completions、Responses、Anthropic Messages |
| 画像理解 | Qwen3-VL dense/MoE、互換画像テキストモデル | AutoModelForImageTextToText または視覚 API |
| 画像拡張・口の参考画像 | FLUX.2 klein 4B/9B | Flux2KleinPipeline、画像条件 |
| 画像拡張 | Qwen-Image-Edit-2511、互換 Edit Plus | QwenImageEditPlusPipeline |
| 声の設計 | Qwen3-TTS 1.7B VoiceDesign | 自然言語から参照音声 |
| ストリーミング音声 | CosyVoice3 0.5B | `speech_service.py`、参照音声と話し方制御 |
| 代替音声 | CosyVoice 300M/2/3、Qwen3-TTS Base・CustomVoice 0.6/1.7B | `family_speech_service.py`、一文単位、クローンまたは名前付き話者 |
| マイク | Whisper tiny/base/small/medium/large-v3/turbo | `whisper_service.py`、自動言語検出または `--language` |
| 前景抽出 | BiRefNet-general ONNX / rembg | `segmentation` のパス |
| 顔の点 | MediaPipe FaceLandmarker | `face_landmarker` の `.task` |
| 音声から表情 | UniTalker v0.4.0 base ONNX | `audio_face`、設定内のチャンネル対応 |
| 任意の 3D | AniGen、DINOv2 ViT-L/14 registers、DSINE/EfficientNet-B5 | AniGen、`dinov2`、`normals` |

`tested` は推論の動作確認済み、`adapter-compatible` は系列ローダーとタスク仕様への対応を示します。MoE の重みは総パラメータ数分の保存領域が必要で、活性パラメータ数は主に token ごとの計算量を表します。固定 ONNX/task は出力契約で選びます。VoiceDesign、Base、CustomVoice は別のタスクです。[音声](voice.md)を参照してください。

## パスと読み込み

優先順位は `AVATAR_<ROLE>_MODEL_PATH` → `models.<role>.path` → `AVATAR_MODEL_ROOT` とリポジトリ・リビジョンです。`~` と環境変数を展開します。モデルの相対パスは作業ディレクトリ、プロンプトとテンプレートは設定ファイルを基準にします。

```json
{"models":{
 "roleplay":{"path":"/srv/models/my-checkpoint","device_map":"auto","dtype":"bfloat16",
             "context":8192,"quantization":"none","template_kwargs":{"enable_thinking":false}},
 "vision":{"path":"/srv/models/my-vl-checkpoint"},
 "tts":{"path":"/srv/models/my-cosyvoice"},
 "asr":{"path":"/srv/models/my-whisper"}}}
```

`repo`、`revision`、`license` で独自チェックポイントを記述します。取得記録からモデルを識別し、作成段階とエクスポートに実際のモデル情報を保持します。`quantization` は `int4`、`int8`、`none`。量子化はモデル環境に対応する bitsandbytes が必要です。GGUF/AWQ/GPTQ は OpenAI 互換サービス経由でも接続できます。自動配置はプロセスに見える GPU を使います。

追加のパスは `image`、`image_edit`、`voice_design`、`voice_clone`、`mesh`、`normals`、`dinov2`、`audio_face`、`segmentation`、`face_landmarker` です。tokenizer、音声エンコーダー、flow、vocoder は親モデルディレクトリから読み込みます。補助資源の URL とハッシュは `configs/*models.lock.json` と `configs/audio-face-model.lock.json` にあります。

新しい系列は既存アダプターを拡張するか、[構成](architecture.md)のテキスト、音声、認識、顔係数、作成段階の契約を実装します。

## モデルごとの概算 VRAM

表は VRAM の計画用概算値で、単位は GiB です。同時サービスの使用量は別途加算します。Dense LLM は 16-bit 重みと文脈の余裕を想定し、画像編集は CPU オフロードと追加 RAM を使う場合があります。顔・前景の固定処理は CPU でも実行でき、RAM は画像サイズに依存します。

| モジュール | カタログ ID | VRAM (GiB) | 状態 |
| --- | --- | --- | --- |
| `asr` | `whisper-base` | 1 | adapter-compatible |
| `asr` | `whisper-tiny` | 1 | adapter-compatible |
| `asr` | `whisper-small` | 2 | tested |
| `asr` | `whisper-large-v3-turbo` | 4 | tested |
| `asr` | `whisper-medium` | 4 | adapter-compatible |
| `asr` | `whisper-large-v3` | 7 | adapter-compatible |
| `image` | `flux2-klein-4b` | 18 | tested |
| `image` | `flux2-klein-9b` | 32 | adapter-compatible |
| `image_edit` | `qwen-image-edit-2511` | 48 | tested |
| `mesh` | `anigen` | 45 | tested |
| `roleplay` | `qwen3-0.6b` | 3 | adapter-compatible |
| `roleplay` | `qwen3-1.7b` | 5 | adapter-compatible |
| `roleplay` | `qwen3-4b` | 10 | adapter-compatible |
| `roleplay` | `coser-8b` | 20 | tested |
| `roleplay` | `qwen3-8b` | 20 | tested |
| `roleplay` | `qwen3-14b` | 34 | adapter-compatible |
| `roleplay` | `qwen3-30b-a3b` | 70 | adapter-compatible |
| `roleplay` | `qwen3-32b` | 74 | adapter-compatible |
| `roleplay` | `coser-70b` | 152 | tested |
| `roleplay` | `qwen3-235b-a22b` | 510 | adapter-compatible |
| `tts` | `cosyvoice1` | 4 | adapter-compatible |
| `tts` | `qwen-tts-0.6b-base` | 4 | adapter-compatible |
| `tts` | `qwen-tts-0.6b-customvoice` | 4 | adapter-compatible |
| `tts` | `cosyvoice2` | 6 | adapter-compatible |
| `tts` | `cosyvoice3` | 6 | tested |
| `tts` | `qwen-tts-1.7b-base` | 8 | tested |
| `tts` | `qwen-tts-1.7b-customvoice` | 8 | adapter-compatible |
| `vision` | `qwen3-vl-2b` | 7 | adapter-compatible |
| `vision` | `qwen3-vl-4b` | 12 | tested |
| `vision` | `qwen3-vl-8b` | 24 | adapter-compatible |
| `vision` | `qwen3-vl-30b-a3b` | 72 | adapter-compatible |
| `vision` | `qwen3-vl-32b` | 76 | tested |
| `vision` | `qwen3-vl-235b-a22b` | 530 | adapter-compatible |
| `voice_design` | `qwen-voice-design` | 8 | tested |

[← ガイド一覧](index.md)
