# Character resources

[English](resources.md) · [简体中文](zh-CN/resources.md) · [日本語](ja/resources.md)

## Demonstration library

| Character | Source | Capabilities |
| --- | --- | --- |
| Haru, Hiyori | [Live2D CubismWebSamples](https://github.com/Live2D/CubismWebSamples/tree/b1de66b0b1f1cb881d95fb6158622aeb6a2827bd) | Native mouth, eye, brow, head/body parameters, physics, expressions and motions |
| RobotExpressive | [three.js / Quaternius / Don McCurdy](https://github.com/mrdoob/three.js/tree/157f0885b8428b5ffe8f6f7309b2d6f59faa1497/examples/models/gltf/RobotExpressive) | Fourteen animations, skeleton and three facial morph targets |

Fixed download URLs and checksums are recorded in `configs/demo-assets.json`. Install the sample resources, create voice references and import them:

```bash
python scripts/fetch_demo_characters.py
# Submit this voice-design stage through your GPU runner; a GPUQ example:
gpuq submit --node auto --name avatar-demo-voices --gpus 1 -- bash "$PWD/scripts/design_demo_voices.sh"
# After the voice job completes:
python scripts/import_demo_characters.py
```

Live2D samples use the [Free Material License](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html) and [Sample Model Terms](https://www.live2d.com/eula/live2d-sample-model-terms_en.html). Cubism Core uses the [Live2D Proprietary Software License](https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html). Voice references and conversational personas are created separately by the framework. RobotExpressive is CC0-1.0.

> This content uses sample data owned and copyrighted by Live2D Inc. The sample data are utilized in accordance with terms and conditions set by Live2D Inc. This content itself is created at the author’s sole discretion.

## Import a Live2D ZIP

Choose **2D character → Upload Live2D ZIP** in the studio. Preserve the directory structure and include:

- `.model3.json` and `.moc3`.
- Textures referenced by the manifest.
- Referenced physics, pose, expression and motion files and their audio.
- Resource attribution/license files, for example in `licenses/`.

A ZIP normally selects one model. For a multi-model archive, set `model_entry` through the import API. Validation checks paths, archive sizes, file references, textures and the moc3 signature. The worker then builds a persona and voice candidates. Select a model compatible with the installed Cubism Core version.

Lip sync uses the manifest's `LipSync` group or `ParamMouthOpenY`. Custom parameter IDs can be mapped in `profile.json` under `live2d_parameter_map`. Playback follows the parameters, native motions and physics available in the imported resource.

## Generated 2D portraits

The image pipeline creates a deformable illustration with a source-lip mesh for continuous mouth movement. It uses its own 2D rig and resource format. Native Cubism models provide model-authored perspective changes, occlusion handling and detailed clothing motion; choose that import route for an authored Live2D performance.

Each character has either `presentation_modes=["2d"]` or `["3d"]`. Create separate characters when you want both types for one persona.

## Character package

Eight core files describe the character: `profile.json`, `capabilities.json`, `rig_map.json`, `face_map.json`, `motion_manifest.json`, `voice_profile.json`, `provenance.json` and `qa_report.json`. Their schemas are in `schemas/`.

Portrait packages include `puppet/`; native Live2D includes `live2d/`; 3D includes `model.glb`. Export preserves referenced assets, voice candidates, license files and provenance. Install the corresponding renderer on the receiving deployment, then validate the restored package with `avatar validate PATH --require-assets`.

[← All guides](index.md)
