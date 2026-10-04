# Voice design and speech quality

[English](voice.md) · [简体中文](zh-CN/voice.md) · [日本語](ja/voice.md)

The default voice pipeline has two stages. Qwen3-TTS VoiceDesign creates a reference voice from the character's description. CosyVoice3 then synthesizes dialogue from that audio reference and its accurate transcript.

VoiceDesign accepts natural-language instructions describing pitch, resonance, texture, articulation, pacing and personality. Its generated voices are independent of CustomVoice's fixed speaker list. Creation offers 3–8 candidates, with five by default; candidate count controls how many variations the user can compare.

## Choose a reference

All candidates read the same character-specific passage. Each retains the main voice brief while exploring a slightly different conversational delivery and seed. Listen for intelligibility, stable identity, natural pauses and the character's personality. The automatic recommendation checks signal quality; the studio lets you choose the voice you prefer.

Change the reference first when the timbre feels wrong. Adjust the persona's speaking habits and emotional intensity when the wording or delivery feels stiff. Reference recordings work best with a single speaker, clear speech and an exact transcript.

## Delivery during conversation

Ordinary conversational emotion uses reference-conditioned zero-shot synthesis. Explicit tone/pace or strong emotion selects restrained CosyVoice3 instruction mode. Each segment can carry:

```json
{"delivery":{"tone":"warm","pace":"relaxed","pause_after_ms":320}}
```

Supported tones are conversational, warm, playful and serious; paces are natural, relaxed and brisk. Paragraph pauses are represented in the audio sample clock, so facial timing remains aligned.

The creation request’s `locale` selects English, Chinese or Japanese persona text and VoiceDesign synthesis. Changing the UI language preserves existing character content. Create a character in the desired language for a matching reference voice.

## Alternative speech models

`services/family_speech_service.py` provides Qwen3-TTS Base 0.6/1.7B voice cloning, CustomVoice 0.6/1.7B named speakers and CosyVoice family loading. These adapters finish a sentence before emitting its PCM blocks. The default CosyVoice3 service emits audio during generation and supports cancellation-aware native token production.

For reference-conditioned multilingual speech, set `models.voice_clone.path` to a Base checkpoint and use this entry in your service-group configuration:

```json
{
  "services": {
    "tts": {
      "python": "${AVATAR_QWEN_PYTHON}",
      "script": "services/family_speech_service.py",
      "model_role": "voice_clone",
      "port": 18120,
      "args": [
        "--backend",
        "qwen-base",
        "--language",
        "Auto"
      ]
    }
  }
}
```

Point `AVATAR_TTS_URL` at the service's forwarded address. `Auto` follows the spoken text; an explicit language such as `Japanese` fixes it for a dedicated installation. Base derives voice identity and delivery from the reference recording. The application schedules expressions, gestures and paragraph pauses independently.

For comparisons, hold reference voice, spoken text and hardware constant. Measure intelligibility, timbre consistency, pauses, prosody and time to the first audio block. Listen to the recordings alongside ASR and signal checks.

Upstream documentation: [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS#voice-design), [CosyVoice](https://github.com/FunAudioLLM/CosyVoice).

[← All guides](index.md)
