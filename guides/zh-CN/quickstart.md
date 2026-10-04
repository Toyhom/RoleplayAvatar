# 快速开始

[English](../quickstart.md) · [简体中文](quickstart.md) · [日本語](../ja/quickstart.md)

按下面四步安装应用、连接模型并开始交谈。如果希望由 Codex 或 Claude Code 完成安装，可以复制[AI 安装说明](ai-setup.md)。

## 1. 安装应用

准备 Git、Python 3.11 和 Node.js 18+。使用语音和角色创建功能时，还需按[安装指南](setup.md)准备 FFmpeg、SoX 和 libsndfile。

克隆仓库后，安装应用并构建界面。如果已经下载仓库，在项目根目录执行即可，跳过前两条命令。

```bash
git clone https://github.com/Toyhom/RoleplayAvatar.git
cd RoleplayAvatar
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[download]'
npm ci
npm run build
```

## 2. 选择并配置模型

| 对话方式 | 需要准备 | 配置说明 |
| --- | --- | --- |
| 厂商 API | 厂商账号、API 密钥和模型名称 | [厂商 API](providers.md) |
| 本地模型 | 模型权重和满足需求的 GPU 显存 | [模型与预设](models.md) · [推理性能](performance.md) |

语音合成、麦克风识别和角色创建各有独立的模型服务。按[安装指南](setup.md)配置需要的功能；对话使用厂商 API 时，其他服务也可以在本地运行。

### 使用厂商 API

按[厂商 API 指南](providers.md)，在 `configs/models.local.json` 中为各智能体填写接口地址、模型名称和密钥环境变量名，然后继续第 3 步。

### 使用本地模型

先查看硬件建议。`--vram-gib` 表示每张 GPU 的显存，请按自己的硬件修改数值：

```bash
.venv/bin/avatar models recommend --vram-gib 24 --gpus 1
```

下面以 `compact` 预设为例下载模型并生成配置。将 `compact` 换成选定的预设，将 `/path/to/models` 换成模型存储目录的绝对路径：

```bash
.venv/bin/avatar models download compact --mirror --model-root /path/to/models
.venv/bin/avatar models configure compact --model-root /path/to/models
```

- `--mirror` 使用 [hf-mirror.com](https://hf-mirror.com)。去掉该参数使用 Hugging Face；其他镜像用 `--endpoint URL` 指定。
- 下载前想先查看清单，可给下载命令加上 `--dry-run`。
- 需要从图片创建角色，或导入 Live2D 并设计声线时，给下载和配置两条命令都加上 `--creation`。
- 配置命令创建 `configs/models.local.json`。已有配置可直接编辑，或用 `--output` 指定新文件。

## 3. 启动模型服务和应用

首次安装时创建部署配置文件：

```bash
cp .local.env.example .local.env
```

编辑 `.local.env`，填写应用环境、模型目录、`configs/models.local.json` 的绝对路径、服务解释器和 `AVATAR_*_URL` 接口地址。以后启动时复用这份文件。

按[安装指南](setup.md)准备所选模型的环境并启动对应服务。本地对话的加速引擎和显存预算见[性能指南](performance.md)。

检查配置并启动应用：

```bash
source scripts/common.sh
"$PYTHON" -m roleplay_avatar.cli doctor
bash scripts/serve.sh
```

打开 [http://localhost:18080](http://localhost:18080)。在 [/api/services](http://localhost:18080/api/services) 确认已配置的服务就绪。使用期间保持服务终端运行；在各终端按 Ctrl+C 可停止对应的前台进程。

## 4. 创建角色并交谈

1. 选择 **2D** 或 **3D**，上传图片和简短描述。2D 角色也可导入完整 Live2D ZIP。
2. 试听生成的候选声线并选择。现成示例的安装方法见[角色资源](resources.md)。
3. 打字或使用麦克风交谈。麦克风需要通过 localhost 或 HTTPS 访问，并允许浏览器录音。
4. 可以打断播放、导出 JSON 或开启主动交谈。每个角色有独立会话；当前会话有实质内容后，可以创建新会话。

## 常见问题

| 遇到的问题 | 检查方法 |
| --- | --- |
| 模型目录不存在 | 执行 `source scripts/common.sh` 加载 `.local.env`，再运行 `"$PYTHON" -m roleplay_avatar.cli doctor`，核对下载位置与配置路径。 |
| 服务未就绪 | 检查对应日志、`/healthz` 和 `AVATAR_*_URL`。 |
| 厂商 API 返回 401 | 检查该智能体指定的密钥环境变量。 |
| 显存不足 | 换较小预设，或把服务分配到不同 GPU；角色创建可单独运行。 |
| 麦克风按钮不可用 | 使用 localhost 或 HTTPS，并检查浏览器录音权限。 |
| 下载需要授权 | 完成模型仓库的访问申请，并用 `--token-env HF_TOKEN` 指定下载凭据。 |

[← 全部指南](index.md)
