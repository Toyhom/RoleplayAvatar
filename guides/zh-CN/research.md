# 角色扮演研究与自定义方法

[English](../research.md) · [简体中文](research.md) · [日本語](../ja/research.md)

可以独立替换角色模型、提示词、生成策略，同时保留语音、渲染、会话存储和导出。从 `configs/research.example.json` 开始，选择以下两种输出模式。

## 直接生成表演

将 `agents.roleplay.output_mode` 设为 `performance`。模型输出逐行 JSON 段落：

```json
{"text":"你还记得我最喜欢的花！", "emotion":"happy", "intensity":0.5,
 "action_intent":"acknowledge", "actions":[{"name":"nod","start_s":0,"duration_s":1.6,"strength":0.5}],
 "delivery":{"tone":"warm","pace":"natural","pause_after_ms":260}}
```

应用增量解析这些段落。可以替换 `prompts.performance`，并保留 `Segment` 契约。

## 角色模型与表演导演

`output_mode: "actor_director"` 让角色模型生成自然对话和舞台指示，`performance_director` 再转换为可播放的段落，分离心理描写与台词、映射受支持动作。此模式适合保留专用模型的原生输出格式。角色回复完整收集后才调用导演，因此直接表演模式的首段延迟更低。

角色模型接收人设和当前会话；历史表演记录转换为台词后放入上下文。`prompts.actor`、`prompts.roleplay`、每个角色的人设可分别修改，导演也有独立提示词与采样设置。默认导演按用户明确要求或用户消息的语言输出；需要保留模型原始语言时，可覆盖 `prompts.performance_director`，或通过 `ModelGateway` 直接评估角色模型。

默认角色提示要求简短台词和动作描述。`agents.roleplay.generation.max_tokens` 控制长度；需要长叙述时，一并调整提示词和输出长度。

## 模型、提示词、推理策略

| 配置项 | 用途 |
| --- | --- |
| `models.<role>.path` | 本地检查点 |
| `agents.<role>` | 接口、协议、模型 ID |
| `agents.<role>.generation` | 采样和长度；本地服务支持 temperature、top_p、repetition_penalty、seed、stop |
| `models.<role>.chat_template` | 本地 Jinja 模板 |
| `models.<role>.template_kwargs` | 模板选项，如思考模式 |
| `models.<role>.eos_token_id` | 自定义训练格式的结束 token ID 或列表 |
| `prompts.<name>` | 字符串或 UTF-8 文件 |

本地加载器同时识别检查点和 tokenizer 的结束 token。通过 `AVATAR_MODELS_CONFIG` 选择配置；提示词文件相对配置路径解析。改变部署条件后重启相关进程，并为新条件创建新会话。

## 统一接口评估

按角色和条件创建独立会话，通过 HTTP NDJSON 流式接收结果并导出完整 JSON。导出包含文本、表演元数据、时间戳、完成或中断状态。只需要模型文本时，也可直接使用网关：

```python
import asyncio
from roleplay_avatar.agents import ModelGateway

async def evaluate():
    output = []
    async for token in ModelGateway("roleplay").stream(
        "你是一位耐心的灯塔守护者。",
        [{"role":"user", "content":"暴风雨就要来了，我们该怎么办？"}],
        max_tokens=500, temperature=0.7,
    ):
        output.append(token)
    return "".join(output)

print(asyncio.run(evaluate()))
```

比较条件时保持人设、参考声线、输入和渲染配置一致，记录检查点版本、提示词和采样设置。端到端延迟包含角色模型、可选导演和首个语音块，研究响应速度时应分别测量。

## 扩展方法

可在 `ModelGateway` 周围实现检索、记忆、规划或多角色协调，也可替换现有协议后面的模型服务。会话归属和回复取消由编排层维护。扩展边界见[架构](architecture.md)，运行和导出见 [API](api.md)。

[← 全部指南](index.md)
