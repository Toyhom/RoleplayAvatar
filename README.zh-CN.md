# 镜界 · Roleplay Avatar

本框架仅供角色扮演对话研究和测试使用，当前版本也较为粗糙。

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

让角色拥有自己的形象、声音和对话。

上传一张图片和简短描述，创建能说话的 2D 角色；也可以导入完整 Live2D 资源，选择声线，通过麦克风交谈。角色回复包含表情、动作和语音节奏，每个角色拥有独立会话，并支持 JSON 导出。开启主动模式后，控制智能体会根据空闲状态和上下文决定何时开口。

框架支持按模块选择本地模型或厂商 API，提供纯后端模式，适合日常体验、应用开发和角色扮演研究。

https://github.com/user-attachments/assets/556ac18a-fe2e-4d63-8d5b-b694ded76a69

**30 秒功能介绍：** [简体中文](README.zh-CN.md) · [English](README.md) · [日本語](README.ja.md)

| 你的目标 | 入口 |
| --- | --- |
| 配置模型并开始交谈 | [快速开始](guides/zh-CN/quickstart.md) |
| 让 Codex / Claude Code 帮忙安装 | [可复制的 AI 安装说明](guides/zh-CN/ai-setup.md) |
| 根据显卡选模型、从国内镜像下载 | [模型与配置](guides/zh-CN/models.md) |
| 完整本地部署 | [详细安装指南](guides/zh-CN/setup.md) |
| 本地推理加速与显存优化 | [性能配置](guides/zh-CN/performance.md) |
| 开发接口与模块 | [API](guides/zh-CN/api.md) · [系统架构](guides/zh-CN/architecture.md) |
| 测试自己的角色扮演模型或提示词 | [研究指南](guides/zh-CN/research.md) |

[全部指南](guides/zh-CN/index.md)

## 创建和交谈

1. 创建时选择 2D 或 3D，上传图片；2D 也可上传完整 Live2D ZIP。
2. 描述角色的性格和声音，试听候选声线并选择。
3. 打字或使用麦克风交谈，回复中的表情和动作会驱动角色。
4. 当前会话有实质内容后即可另开新会话，也可导出完整 JSON 记录。

[角色资源](guides/zh-CN/resources.md)介绍官方 Haru、Hiyori、RobotExpressive 示例和原生 Live2D 导入。[声线设计](guides/zh-CN/voice.md)说明参考声音与在线合成的关系。

## 模型与授权

硬件预设覆盖单卡和多卡部署，按模块列出支持的模型与资源需求。可分别配置角色对话、主动判断、人设设计和表演解析；支持 DeepSeek、Qwen、OpenAI、Claude，以及 OpenAI 兼容推理服务。

原创代码采用 [MIT](LICENSE)。模型、依赖和资源的来源及授权集中列在 [NOTICE](NOTICE.md)。
