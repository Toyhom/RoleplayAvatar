# 角色资源

[English](../resources.md) · [简体中文](resources.md) · [日本語](../ja/resources.md)

## 演示资源库

| 角色 | 来源 | 能力 |
| --- | --- | --- |
| Haru、Hiyori | [Live2D CubismWebSamples](https://github.com/Live2D/CubismWebSamples/tree/b1de66b0b1f1cb881d95fb6158622aeb6a2827bd) | 原生嘴、眼、眉、头身参数、物理、表情、动作 |
| RobotExpressive | [three.js / Quaternius / Don McCurdy](https://github.com/mrdoob/three.js/tree/157f0885b8428b5ffe8f6f7309b2d6f59faa1497/examples/models/gltf/RobotExpressive) | 14 个动画、骨骼、3 个面部形变目标 |

固定下载链接和校验值见 `configs/demo-assets.json`。安装、生成参考声线和导入：

```bash
python scripts/fetch_demo_characters.py
# 通过 GPU 任务调度器运行声线生成；GPUQ 示例：
gpuq submit --node auto --name avatar-demo-voices --gpus 1 -- bash "$PWD/scripts/design_demo_voices.sh"
# 声线任务完成后：
python scripts/import_demo_characters.py
```

Live2D 示例采用 [Free Material License](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html) 和 [Sample Model Terms](https://www.live2d.com/eula/live2d-sample-model-terms_en.html)。Cubism Core 使用 [Live2D Proprietary Software License](https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html)。框架分别创建参考声音和对话人设。RobotExpressive 为 CC0-1.0。

> This content uses sample data owned and copyrighted by Live2D Inc. The sample data are utilized in accordance with terms and conditions set by Live2D Inc. This content itself is created at the author’s sole discretion.

## 导入 Live2D ZIP

界面中选择 **2D 角色 → 上传完整 Live2D ZIP**。保留目录结构并包含：

- `.model3.json`、`.moc3`。
- 清单引用的纹理。
- 引用的物理、姿势、表情、动作文件及相关音频。
- 资源来源和授权文件，例如放在 `licenses/`。

一般一个 ZIP 对应一个模型，多模型可通过 API 的 `model_entry` 选择。验证包括路径、压缩包大小、引用完整性、纹理和 moc3 签名。然后自动生成角色设定与候选声线。模型须与安装的 Cubism Core 版本兼容。

口型使用清单的 `LipSync` 分组或 `ParamMouthOpenY`。自定义参数可在 `profile.json` 的 `live2d_parameter_map` 中映射。表演使用模型自身的参数、动作和物理绑定。

## 自动生成的 2D 立绘

图片流程创建可形变的立绘，利用原图嘴部网格实现连续口型，使用框架自己的 2D 绑定格式。原生 Cubism 模型具备作者制作的透视变化、遮挡关系和服饰动态；需要这类表现时可选择 Live2D 导入。

每个角色只声明 `presentation_modes=["2d"]` 或 `["3d"]`；两种类型应分别创建。

## 角色包

八个核心文件：`profile.json`、`capabilities.json`、`rig_map.json`、`face_map.json`、`motion_manifest.json`、`voice_profile.json`、`provenance.json`、`qa_report.json`。机器契约在 `schemas/`。

立绘包包含 `puppet/`，Live2D 包包含 `live2d/`，3D 包包含 `model.glb`。导出保留引用资源、候选声音、授权文件和来源。接收端安装对应渲染器后运行 `avatar validate PATH --require-assets`。

完整来源与授权见 [NOTICE](../../NOTICE.md)。

[← 全部指南](index.md)
