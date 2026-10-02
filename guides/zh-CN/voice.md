# 声线设计与语音质量

[English](../voice.md) · [简体中文](voice.md) · [日本語](../ja/voice.md)

默认语音链分为两步：Qwen3-TTS VoiceDesign 根据角色描述生成参考声音，CosyVoice3 根据参考音频和准确文本合成对话。

VoiceDesign 接收音域、共鸣、音质、吐字、语速和性格等自然语言要求。它与 CustomVoice 的固定说话人列表是两种任务。创建时提供 3–8 个声线候选，默认 5 个；数量决定可试听的变体数。

## 选择参考声音

候选声音朗读同一段角色台词，在保留主要声线要求的同时改变语气和随机种子。重点听清晰度、身份稳定性、停顿以及是否符合性格。自动推荐根据音频信号质量选出初始项，最终可以在界面中试听选择。

音色不合适时先换参考声线。台词或语气僵硬时调整人设的说话习惯与情感强度。清晰的单人录音和准确对应的文本有利于保持声音一致。

## 对话中的表达

普通情绪使用参考音频条件下的零样本合成；指定语调、语速或较强情感时使用适度的 CosyVoice3 指令控制。每段可包含：

```json
{"delivery":{"tone":"warm","pace":"relaxed","pause_after_ms":320}}
```

`tone` 支持 `conversational`、`warm`、`playful`、`serious`；`pace` 支持 `natural`、`relaxed`、`brisk`。段落停顿会计入音频采样时钟，表情保持同步。

创建时的 `locale` 决定参考台词及 VoiceDesign 的语言：`en`、`zh-CN`、`ja`。切换界面语言保留已有角色内容；需要其他语言的参考声线时，可按该语言新建角色。

## 替换语音模型

`services/family_speech_service.py` 支持 Qwen3-TTS Base 0.6/1.7B 的参考声音克隆、CustomVoice 0.6/1.7B 的内置说话人，以及 CosyVoice 系列加载。此适配器先合成一整句，再输出 PCM 分块；默认 CosyVoice3 服务在生成中流式输出，支持中断原生 token 生成。

使用参考声线进行多语言合成时，将 `models.voice_clone.path` 指向 Base 检查点，并在服务组配置中加入：

```json
"tts": {
  "python": "${AVATAR_QWEN_PYTHON}",
  "script": "services/family_speech_service.py",
  "model_role": "voice_clone",
  "port": 18120,
  "args": ["--backend", "qwen-base", "--language", "Auto"]
}
```

将 `AVATAR_TTS_URL` 指向该服务转发后的地址。`Auto` 根据台词选择语言；专用部署也可以明确设置 `Japanese` 等语言。Base 从参考录音获取音色和说话方式，表情、动作及段落停顿仍由应用独立调度。

比较效果时固定参考音频、文本和硬件，记录可懂度、音色一致性、停顿、韵律与首个音频块延迟，同时试听实际录音并参考 ASR、音频信号检查。

上游资料：[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS#voice-design)、[CosyVoice](https://github.com/FunAudioLLM/CosyVoice)。配置见[模型](models.md)与[供应商](providers.md)。

[← 全部指南](index.md)
