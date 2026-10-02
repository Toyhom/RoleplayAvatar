# 声の設計と音声品質

[English](../voice.md) · [简体中文](../zh-CN/voice.md) · [日本語](voice.md)

既定の音声処理は二段階です。Qwen3-TTS VoiceDesign がキャラクターの説明から参照音声を作成し、CosyVoice3 がその音声と正確な書き起こしから会話を合成します。

VoiceDesign は音域、共鳴、質感、発音、速度、性格などの自然言語指定を受け取ります。CustomVoice の固定話者とは異なるタスクです。作成時に 3–8 種類、既定では 5 種類の候補を生成し、比較できます。

## 参照音声を選ぶ

候補は同じキャラクター用の台詞を読み、声の主要な指定を維持しながら話し方とシードを変えます。明瞭さ、声の一貫性、自然な間、性格との相性を確認してください。自動選択は信号品質を基準に初期候補を選び、画面で試聴して変更できます。

声質が合わなければ参照音声を変更します。言葉や話し方が硬い場合は、設定の話し方や感情の強度を調整します。明瞭な単一話者の録音と正確な書き起こしが、安定した合成に適しています。

## 会話中の表現

通常の感情は参照音声を条件とするゼロショット合成を使います。明示的な声の調子・速度、または強い感情は CosyVoice3 の指示モードで制御します。

```json
{"delivery":{"tone":"warm","pace":"relaxed","pause_after_ms":320}}
```

`tone` は `conversational`、`warm`、`playful`、`serious`、`pace` は `natural`、`relaxed`、`brisk` に対応します。段落間の休止も音声サンプル時刻に含まれ、表情が同期します。

作成時の `locale` は参照台詞と VoiceDesign の言語を選びます：`en`、`zh-CN`、`ja`。画面の言語を変えても既存キャラクターの内容は保持されます。別の言語の参照音声が必要なら、その言語で新しいキャラクターを作成できます。

## 音声モデルの差し替え

`services/family_speech_service.py` は Qwen3-TTS Base 0.6/1.7B の参照音声クローン、CustomVoice 0.6/1.7B の内蔵話者、CosyVoice 系列を読み込めます。このアダプターは一文を合成してから PCM を分割送信します。既定の CosyVoice3 サービスは生成中に音声を送り、ネイティブの token 生成を中断できます。

参照音声を使って多言語で合成する場合、`models.voice_clone.path` に Base チェックポイントを指定し、サービスグループに次の設定を加えます。

```json
"tts": {
  "python": "${AVATAR_QWEN_PYTHON}",
  "script": "services/family_speech_service.py",
  "model_role": "voice_clone",
  "port": 18120,
  "args": ["--backend", "qwen-base", "--language", "Auto"]
}
```

`AVATAR_TTS_URL` をサービスの転送先アドレスに設定します。`Auto` は台詞から言語を選びます。専用構成では `Japanese` などを明示できます。Base は参照録音から声質と話し方を取り込み、表情、動作、段落間の休止はアプリが個別に制御します。

比較では参照音声、台詞、ハードウェアを固定します。明瞭さ、声質の一貫性、間、韻律、最初の音声ブロックまでの時間を測り、実際の録音と ASR・信号のチェックを確認します。

上流資料：[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS#voice-design)、[CosyVoice](https://github.com/FunAudioLLM/CosyVoice)。設定は[モデル](models.md)と[プロバイダー](providers.md)を参照してください。

[← ガイド一覧](index.md)
