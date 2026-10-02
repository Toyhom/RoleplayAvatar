# 模型供应商与配置

[English](../providers.md) · [简体中文](providers.md) · [日本語](../ja/providers.md)

每个智能体可以单独选择供应商、模型、生成参数和提示词。一个通用模型可以服务全部智能体，也可以把角色模型与控制模型分开。

## 连接一个供应商

创建 `configs/models.local.json`：

```json
{"agents":{"default":{"provider":"qwen","model":"qwen-plus","require_key":true,
                        "extra_body":{"enable_thinking":false}}}}
```

在环境或私有 `.local.env` 中设置：

```bash
export AVATAR_MODELS_CONFIG="$PWD/configs/models.local.json"
export DASHSCOPE_API_KEY='your-key'
```

重启 Web 进程使智能体设置生效；新创建任务启动时读取配置。

| provider | 协议 | 默认地址 | 密钥变量 |
| --- | --- | --- | --- |
| `deepseek` | OpenAI Chat Completions | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |
| `qwen` | OpenAI Chat Completions | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` |
| `openai` | OpenAI Chat Completions | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| `anthropic` / `claude` | Anthropic Messages | `https://api.anthropic.com/v1` | `ANTHROPIC_API_KEY` |
| `openai-compatible` | OpenAI Chat Completions | `http://127.0.0.1:8000/v1` | `AVATAR_LLM_API_KEY` |
| `local` | `/chat` NDJSON | `http://127.0.0.1:18110` | 可选 `AVATAR_LLM_API_KEY` |

`model` 填账户中可调用的模型 ID。用 `url` 指定地区端点、代理、vLLM、SGLang 或 llama.cpp。无需认证的本地接口设为 `require_key:false`。

## 各模块独立路由

```json
{
  "agents": {
    "default":{"provider":"qwen","model":"qwen-plus"},
    "roleplay":{"provider":"openai-compatible","url":"http://localhost:8000/v1",
                "model":"my-roleplay-checkpoint","output_mode":"actor_director","require_key":false},
    "performance_director":{"generation":{"temperature":0.2}},
    "initiative":{"provider":"deepseek","model":"deepseek-chat"},
    "character_design":{"provider":"anthropic","model":"YOUR_CLAUDE_MODEL_ID"},
    "voice_direction":{"provider":"openai","model":"YOUR_OPENAI_MODEL_ID"}
  }
}
```

`agents.<role>` 覆盖 `agents.default`。更换供应商时重置继承的端点、密钥变量、模型 ID 和供应商扩展，因此须显式填写该供应商的模型 ID。保留供应商时，`generation`、`extra_body` 的字段合并。

`performance` 让角色模型直接生成表演 JSON；`actor_director` 先生成自然回复，再交给 `performance_director` 提取台词、表情和动作。参见[研究指南](research.md)。

## 生成与协议选项

`generation` 可设置 `temperature`、`top_p`、`max_tokens`、`seed` 及服务商支持的参数，配置优先于调用默认值。值为 `null` 时省略该参数，适合固定采样策略的模型。

`extra_body` 传递扩展参数，例如 `enable_thinking`；消息、模型和路由由网关负责。推理过程与可朗读文本分开处理。

OpenAI Responses 示例：

```json
{"provider":"openai", "backend":"openai-responses", "model":"YOUR_MODEL_ID",
 "generation":{"temperature":null, "max_tokens":1400}}
```

网关将 `max_tokens` 映射为 `max_output_tokens`。Chat Completions 的新式长度字段可设置 `max_tokens_field:"max_completion_tokens"`。Anthropic 使用原生 `/messages`、`x-api-key` 和文本流。`timeout_s` 设置超时。

可以注册自己的供应商：

```json
{"providers":{"lab":{"backend":"openai","url":"https://models.example.org/v1",
                        "api_key_env":"LAB_MODEL_KEY"}},
 "agents":{"default":{"provider":"lab","model":"research-model"}}}
```

## 视觉理解 API

```json
{"models":{"vision":{"adapter":"api"}},
 "agents":{"vision":{"provider":"qwen","model":"qwen-vl-plus"}}}
```

创建工作进程向该智能体发送上传图片和设计提示词，支持 OpenAI 兼容与 Anthropic 图片消息。图像合成和语音使用各自的适配器，契约见[架构](architecture.md)。

## 提示词文件

`prompts` 支持字符串或相对 JSON 配置路径的文件：

```json
{"prompts":{"actor":{"file":"../prompts/local/actor.txt"},
            "initiative":"判断此刻是否适合简短地延续这段对话。"}}
```

默认文件在 `src/roleplay_avatar/prompt_templates/`。名称包括 `roleplay`、`actor`、`performance`、`performance_director`、`initiative`、`character_design`、`voice_direction`、`vision`、`image_2d`、`image_3d`。视觉模板支持 `{description}`，图像模板支持 `{appearance}`。角色专属人设保存在角色包中。

示例：[混合供应商](../../configs/providers.example.json)、[研究配置](../../configs/research.example.json)、[全部模型路径](../../configs/models.example.json)。

[← 全部指南](index.md)
