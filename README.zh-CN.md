# 镜界 · Roleplay Avatar

本框架仅供角色扮演对话研究和测试使用，当前版本也较为粗糙。

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

让角色拥有自己的形象、声音和对话。

上传一张图片和简短描述，创建能说话的 2D 角色；也可以导入完整 Live2D 资源，选择声线，通过麦克风交谈。角色回复包含表情、动作和语音节奏，每个角色拥有独立会话，并支持 JSON 导出。开启主动模式后，控制智能体会根据空闲状态和上下文决定何时开口。

框架连接可替换的角色扮演、角色设计、语音和动画模型，可使用本地模型、厂商 API，或混合部署。纯后端 API 提供相同的角色创建和对话流程，方便应用开发和角色扮演研究。

https://github.com/user-attachments/assets/063966a0-8026-4ea3-9808-e0718b1cb242

**30 秒功能介绍：** [English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

[全部指南](guides/zh-CN/index.md)

## 从这里开始

| 你的目标 | 入口 |
| --- | --- |
| 配置模型并开始交谈 | [快速开始](guides/zh-CN/quickstart.md) |
| 让 Codex / Claude Code 帮忙安装 | [可复制的 AI 安装说明](guides/zh-CN/ai-setup.md) |
| 根据硬件选择模型 | [模型、预设与下载](guides/zh-CN/models.md) |
| 接入 DeepSeek、Qwen、OpenAI 或 Claude | [厂商 API 与配置](guides/zh-CN/providers.md) |
| 完整本地部署 | [详细安装指南](guides/zh-CN/setup.md) |
| 本地推理加速与显存优化 | [性能配置](guides/zh-CN/performance.md) |
| 开发接口与模块 | [API](guides/zh-CN/api.md) · [系统架构](guides/zh-CN/architecture.md) |
| 测试自己的角色扮演模型或提示词 | [研究指南](guides/zh-CN/research.md) |

## 创建和交谈

1. 创建时选择 **2D** 或 **3D**，上传图片；2D 也可上传完整 Live2D ZIP。
2. 描述角色的性格和声音，试听候选声线并选择。
3. 打字或使用麦克风交谈，回复中的表情和动作会驱动角色。
4. 当前会话有实质内容后即可另开新会话，也可导出完整 JSON 记录。

[角色资源](guides/zh-CN/resources.md)介绍原生 Live2D 导入和官方 Haru、Hiyori、RobotExpressive 示例资产。[声线设计](guides/zh-CN/voice.md)说明如何塑造角色的声音。

## 模型选择

硬件预设覆盖单卡配置和更大的多卡部署。模型目录列出各模型系列的不同规格，并提供固定版本的下载：

```bash
.venv/bin/avatar models recommend --vram-gib 24 --gpus 1
.venv/bin/avatar models download compact --mirror --model-root /path/to/models
.venv/bin/avatar models configure compact --model-root /path/to/models
```

每个智能体可独立配置 OpenAI Chat Completions、OpenAI Responses、Anthropic Messages 或框架自带的本地协议。提示词、生成参数和模型路径分别配置。

## 许可证

框架原创代码采用 [MIT](LICENSE)。模型和资源的来源及许可证列在 [NOTICE](NOTICE.md)。
