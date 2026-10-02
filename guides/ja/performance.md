# ローカル推論と性能設定

[English](../performance.md) · [简体中文](../zh-CN/performance.md) · [日本語](performance.md)

ローカルモデルごとに実行環境と VRAM 予算を設定します。同じチェックポイントを使うエージェントは推論サービスを共有でき、対話、自発的な会話の判断、キャラクター設定の生成が一組の重みを再利用します。モデル提供元の API は[プロバイダー設定](providers.md)を使用します。

## ランタイムを選ぶ

| モジュール | ランタイム | 主な設定 |
| --- | --- | --- |
| 対話・制御エージェント | vLLM | 連続バッチ処理、プレフィックスキャッシュ、分割プリフィル、テンソル並列、重みと KV キャッシュの量子化 |
| 対話・対応する視覚モデル | SGLang | 連続バッチ処理、RadixAttention キャッシュ、テンソル並列、量子化 |
| GGUF 対話モデル | llama.cpp `llama-server` | 重み/KV キャッシュの量子化、GPU への部分オフロード、CPU/GPU 実行、並列スロット |
| Transformers 対話 | 付属の `llm_service.py` | SDPA、BF16/FP16、bitsandbytes INT4/INT8、デバイス配置 |
| Whisper 音声認識 | faster-whisper / CTranslate2 | FP16/INT8、ビーム幅、CPU/GPU の選択 |
| Qwen3-TTS | ネイティブ Torch | SDPA / FlashAttention 2、計算精度、参照音声の条件キャッシュ |
| CosyVoice3 | ネイティブ / TensorRT | ストリーミング合成、FP16、TensorRT flow エンジン |
| 画像生成 | Diffusers / Accelerate | モデル単位/逐次 CPU オフロード、VAE タイリング/スライシング、コンパイル |
| 音声から表情 | ONNX Runtime | 独立した CUDA 推論サービス |

モデル構造と量子化形式の対応はランタイムのバージョンと GPU に依存します。[vLLM](https://docs.vllm.ai/en/latest/models/supported_models.html)、[SGLang](https://docs.sglang.ai/supported_models/generative_models.html)、[llama.cpp](https://github.com/ggml-org/llama.cpp) の対応一覧を確認してください。視覚モデルには `agents.vision` と `models.vision.adapter="api"` を設定して画像メッセージを送ります。

## vLLM で始める

専用の Python 3.11 環境を作り、設定を生成します。

```bash
bash scripts/install_model_env.sh vllm /absolute/python3.11 /srv/envs/avatar-vllm
.venv/bin/avatar models configure compact --engine vllm \
  --inference-python /srv/envs/avatar-vllm/bin/python \
  --model-root /srv/models --output configs/models.local.json
export AVATAR_MODELS_CONFIG="$PWD/configs/models.local.json"
.venv/bin/avatar inference plan --role roleplay
```

[モデルカタログ](models.md)から重みをダウンロードします。`inference plan` は起動コマンドと対応するエージェント接続設定を表示します。GPU ランナーで次を実行します。

```bash
.venv/bin/avatar inference start --role roleplay
```

共有 GPUQ サーバーでは、自分のアカウントで `gpuq submit --node auto --gpus N -- /absolute/path/to/.venv/bin/avatar inference start --role roleplay` を送信します。割り当てられた CUDA デバイスを継承し、`tensor_parallel` を割り当て GPU 数に合わせます。キューへの送信には実行ファイルの絶対パスを使用します。

インストーラーは `requirements/vllm.txt` の固定バージョンを使い、新しい環境にインストール済みパッケージを記録します。推論環境は独立した Torch 依存関係を持ち、CPU アプリは `.venv` を使います。SGLang ではインストーラーの種類と `--engine` を `sglang` に変更します。

vLLM インストーラーはフレームワークのデバイスプラグインも登録します。vLLM 0.21 では、割り当て GPU UUID を NVML で解決し、`CUDA_VISIBLE_DEVICES` を維持します。

## メモリと同時実行数

[inference.example.json](../../configs/inference.example.json) を参考にしてください。`models` は重み、`inference` はローカルプロセス、`agents` はリクエストの接続先を指定します。複数のエージェントが一つの推論プロセスを共有できます。`avatar doctor` は設定とローカルパスを検査します。

| 設定 | 効果と初期値の目安 |
| --- | --- |
| `context` | リクエストごとの入力と出力の合計 token 数。4096–8192 から調整します。 |
| `gpu_memory_utilization` | vLLM の GPU ごとのメモリ予算、SGLang の静的メモリ比率。音声や一時領域の余裕を確保します。 |
| `max_sequences` | 同時に処理するリクエスト数。対話用途は 1–4 が目安です。 |
| `max_batch_tokens` | vLLM のバッチ token 予算 / SGLang のプリフィル分割サイズ。2048 から調整します。 |
| `prefix_caching` | キャラクター設定などの共通プレフィックスを再利用します。 |
| `chunked_prefill` | 長い入力を分割し、進行中の回答生成と交互に処理します。 |
| `tensor_parallel` | 割り当て GPU 間で一つのモデルを分割します。 |
| `quantization` | `awq`、`gptq`、`fp8` など、チェックポイントとランタイムに適した重み形式。 |
| `kv_cache_dtype` | 重みとは独立したキャッシュ精度。対応する vLLM/SGLang では `fp8` を選べます。 |
| `cpu_offload_gb` | CPU に置く重みの量。VRAM を節約し、転送量が増えます。 |
| `enforce_eager` | CUDA graph を無効化し、グラフ用メモリとスループットを調整します。 |
| `chat_template`、`template_kwargs` | モデル用の会話テンプレートと生成モード設定。 |
| `extra_args` | JSON 文字列配列で指定するネイティブ起動引数。 |

VRAM は重み、KV キャッシュ、CUDA graph、中間テンソル、他のサービスに使われます。以下は十進 GB による**重みのみの理論値**です。

| パラメーター数 | 16-bit | 8-bit | 4-bit |
| --- | ---: | ---: | ---: |
| 4B | 8 | 4 | 2 |
| 8B | 16 | 8 | 4 |
| 32B | 64 | 32 | 16 |
| 70B | 140 | 70 | 35 |

量子化にはスケールとメタデータも必要です。KV キャッシュはコンテキスト長と同時実行数に比例して増えます。大きな事前割り当てキャッシュは、単一リクエストの Transformers より多くの VRAM を使う場合があります。音声と GPU を共有するときは予算を下げ、キャラクター生成は別の割り当てか別の時間帯で実行します。

## GGUF と小容量 GPU

デバイスに適した [llama-server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server) をインストールまたはビルドします。`models.roleplay.path` に GGUF ファイルを指定し、`inference.roleplay` に次を設定します。

```json
{
  "engine": "llama.cpp", "executable": "/srv/llama.cpp/build/bin/llama-server",
  "served_model": "avatar-roleplay", "port": 18110,
  "context": 4096, "max_sequences": 1, "gpu_layers": -1,
  "kv_cache_dtype": "q8_0"
}
```

エージェントはサンプル設定の OpenAI 互換接続を使用します。`gpu_layers=0` は CPU、正の値は指定数の層を GPU に配置します。重みの量子化は GGUF ファイルで決まります。並列スロットの総コンテキストは `context × max_sequences` です。追加の llama.cpp 引数は `extra_args` で渡します。

## 音声と画像の最適化

**音声認識：**`faster-whisper` 環境をインストールし、CTranslate2 形式の Whisper を使います。Transformers 形式は、CTranslate2、Transformers、Torch を備えた環境で変換できます。

```bash
ct2-transformers-converter --model /srv/models/whisper \
  --output_dir /srv/models/whisper-ct2 --quantization float16 \
  --copy_files tokenizer.json preprocessor_config.json
/srv/envs/avatar-faster-whisper/bin/python services/faster_whisper_service.py \
  --model /srv/models/whisper-ct2 --compute-type int8_float16 --port 18140
```

準備完了前にウォームアップします。`--no-warmup` で省略できます。既存の `/transcribe` プロトコルと自動言語検出を維持します。`--beam-size 1` は低遅延向けで、ビーム幅を増やすと認識が改善する場合があります。CPU では `--device cpu --compute-type int8` を指定します。CUDA/cuDNN の条件は [faster-whisper](https://github.com/SYSTRAN/faster-whisper) を参照してください。

**Qwen3-TTS：**`family_speech_service.py --backend qwen-base` は参照音声の条件を最大八件キャッシュします。音声やテキストの変更で対応するキャッシュを更新します。`--voice-cache-size 0` で無効化でき、`/healthz` にヒット数を表示します。`--attention sdpa`、または対応する FlashAttention を導入した環境で `--attention flash_attention_2` を選び、`--dtype` で精度を設定します。文ごとに音声を生成し、連続した 24 kHz PCM として分割送信します。

**CosyVoice3：**`speech_service.py --fp16` は半精度推論、`--tensorrt` は上流の flow エンジンを有効にします。専用環境に対応する TensorRT を導入します。対象 GPU で起動時にエンジンを構築し、そのデプロイと一緒に保存します。[CosyVoice](https://github.com/FunAudioLLM/CosyVoice) を参照してください。

**画像：**`models.image.offload` または `models.image_edit.offload` は `model`（既定）、`sequential`（常駐 VRAM を減らし転送を増やす）、`none`（GPU 常駐）を選べます。VAE が対応している場合、`vae_tiling` と `vae_slicing` は既定で有効です。`compile=true` と `offload="none"` は Torch コンパイルを使い、同じ形状を繰り返す場合に適しています。コールドスタート時間は増えます。通常の作成ワーカーは各段階を別プロセスで実行します。

## 自分の環境で測定する

比較時はモデル、プロンプト、コンテキスト、出力上限を揃えます。

```bash
.venv/bin/python scripts/benchmark_inference.py \
  --url http://127.0.0.1:18110/v1 --model avatar-roleplay \
  --requests 8 --concurrency 4 --max-tokens 128 \
  --template-kwargs '{"enable_thinking":false}' \
  --output outputs/benchmarks/vllm-c4.json
```

付属の Transformers サービスは `--backend local --url http://127.0.0.1:18110` で測定します。結果にはウォームアップ後の最初の文字列までの遅延、全体の遅延、失敗数、出力文字数、サーバーが報告した token スループットが含まれます。`--prompt` と同時実行数を実際の負荷に合わせます。量子化や精度は品質にも影響するため、割り込みと音声の明瞭さも確認してください。

サービスグループの各サービスは `env` オブジェクトでライブラリパスを設定できます。各子プロセスは割り当て済み CUDA デバイスを維持します。

[← ガイド一覧](index.md)
