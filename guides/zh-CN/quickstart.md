# 快速开始

[English](../quickstart.md) · [简体中文](quickstart.md) · [日本語](../ja/quickstart.md)

先选择你的使用方式：CPU 预览可以直接了解界面；真实交谈需要角色模型与语音服务；图片创建还需要图像和声线设计模型。想让 AI 执行安装，可以复制[这份说明](ai-setup.md)。

## 1. 安装界面

在项目根目录执行，准备 Python 3.11 与 Node.js 18+：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,download]'
npm ci
npm run build
AVATAR_MODE=replay .venv/bin/python -m uvicorn roleplay_avatar.app:create_app --factory --port 18080
```

打开 http://localhost:18080，选择角色发送消息。此时使用固定台词与诊断音。切换真实模型前按 Ctrl+C 停止服务。

## 2. 配置真实模型

查看硬件建议，`--vram-gib` 是单张显卡的显存：

```bash
.venv/bin/avatar models recommend --vram-gib 24 --gpus 1
.venv/bin/avatar models download compact --mirror --model-root /path/to/models --dry-run
```

去掉 `--dry-run` 开始下载。`--mirror` 使用 https://hf-mirror.com，下载可断点续传并校验权重。添加 `--creation` 可下载图片创建所需模型。配置厂商 API、选择不同档位和创建配置文件的步骤见[模型与配置](models.md)。

本地对话可按[性能指南](performance.md)选择加速引擎并设置显存预算。

随后按[详细安装指南](setup.md)安装独立的模型环境，启动服务并设置 `AVATAR_*_URL`，再执行 `bash scripts/serve.sh`。该指南也包含原生 Live2D 示例安装和纯后端模式。

## 3. 创建角色并交谈

选择 2D 或 3D，上传图片和简述；已有 Live2D 资源可以打包 ZIP 导入。创建过程会扩充人设、生成 3–8 个候选声线并完成绑定。试听后选择喜欢的声音。

每个角色拥有独立会话。使用麦克风时，通过 localhost 或 HTTPS 打开页面并允许浏览器录音。可以打断播放、导出 JSON，也可以按会话开启主动交谈。

| 遇到的问题 | 检查方法 |
| --- | --- |
| 模型目录不存在 | 加载 `.local.env` 后运行 `avatar doctor`，核对下载位置与配置路径。 |
| 服务未就绪 | 检查对应服务日志、`/healthz` 和 `AVATAR_*_URL`。 |
| 厂商 API 返回 401 | 检查该智能体指定的密钥环境变量。 |
| 显存不足 | 换较小预设，或把在线服务与创建任务放到不同 GPU 分配中。 |
| 麦克风按钮不可用 | 使用 localhost / HTTPS，并检查浏览器权限。 |

[← 全部指南](index.md)
