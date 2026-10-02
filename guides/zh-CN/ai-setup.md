# 让 Codex / Claude Code 帮你安装

[English](../ai-setup.md) · [简体中文](ai-setup.md) · [日本語](../ja/ai-setup.md)

vLLM、SGLang、llama.cpp 和各模块显存参数见[本地推理与性能配置](performance.md)。

在 AI 编程工具中打开本仓库，复制下面这段文字。有偏好时填入目录和模型，其他项可由 AI 检查机器后推荐。

```text
请在当前仓库安装 Roleplay Avatar，并验证真实可用的系统。
目标：2D 角色交谈、原生 Live2D 导入、麦克风输入。
模型目录：[填写，或根据机器推荐]
新环境目录：[填写，或推荐一个独立目录]
模型选择：[按硬件推荐 / compact / balanced / quality / showcase / 厂商 API]
下载源：[国内 https://hf-mirror.com / Hugging Face / 其他镜像]
首选语言：中文。

先阅读 README.md、guides/setup.md、guides/models.md、guides/performance.md 和工作区的适用指令。
检查 Python、Node、GPU 当前可用性、磁盘和已有模型，复用完整兼容的权重。
如果机器已有 GPU 队列，按照其账户和队列流程提交任务。

1. 说明选择的在线模型、创建模型、显存预算以及同时运行的服务。
   使用厂商 API 时确认模型 ID、区域端点和所需密钥变量。
   本地对话按硬件选择 vLLM、SGLang 或 llama.cpp，设置上下文、并发数和显存预算。
   使用相同权重的智能体共享一个推理端点。
2. 在指定位置创建独立环境，安装 Web、构建前端并运行 CPU 测试。
   按部署指南分别安装模型服务依赖。
3. 使用 avatar models recommend/list/download/configure 选择与下载。
   先查看下载计划，再从指定镜像下载固定版本并校验文件。
   安装角色创建需要的上游代码、面部定位和前景分离资源。
4. 写好私有 .local.env 和 configs/models.local.json，填真实路径、解释器、
   每个智能体的模型和服务 URL。密钥值通过私有环境变量提供。
   自由文本角色模型使用 actor_director，其他控制任务使用通用指令模型。
5. 启动模型服务和 Web，检查各服务的健康接口与 /api/services。
   如使用官方 Live2D 示例，下载资源、生成参考声线，再导入角色库。
6. 验证真实回复、语音播放、表情动作、打断、新会话和 JSON 导出；
   同时验证麦克风，以及所选配置中的角色创建或导入流程。
7. 报告访问地址、实际模型、测试结果与准确的启动/停止命令。
   遇到失败时继续排查，或明确指出失败步骤及具体缺失条件。

如果我选择纯后端或自带研究模型，请分别参考 guides/api.md 和
 guides/research.md，独立配置角色模型、提示词和生成参数。
```

进一步了解配置可阅读[模型与配置](models.md)，详细安装步骤见[安装指南](setup.md)。

[← 全部指南](index.md)
