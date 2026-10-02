# Sources and licenses

Original Roleplay Avatar framework code uses the [MIT license](LICENSE). The following components retain their upstream licenses. Exact source commits, model revisions, resource URLs and checksums are recorded in `configs/` and the [model catalog](src/roleplay_avatar/data/models.json).

| Component | Source | License / resource terms |
| --- | --- | --- |
| Qwen3, Qwen3-VL, Qwen Image Edit | [Qwen](https://huggingface.co/Qwen) | Per-checkpoint license recorded in the catalog; current selected checkpoints use Apache-2.0 |
| CoSER | [Neph0s/CoSER](https://github.com/Neph0s/CoSER), [models](https://huggingface.co/Neph0s) | Model card: MIT; Llama 3.1 base: [Llama 3.1 Community License](https://www.llama.com/llama3_1/license/) |
| FLUX.2 klein 4B / 9B | [Black Forest Labs](https://huggingface.co/black-forest-labs) | 4B: Apache-2.0; 9B: FLUX Non-Commercial License |
| Qwen3-TTS | [QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) | Apache-2.0 |
| CosyVoice | [FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice) | Apache-2.0 |
| Whisper | [OpenAI Whisper](https://github.com/openai/whisper), [model repositories](https://huggingface.co/openai) | MIT source; checkpoint license metadata in the catalog |
| Transformers, Diffusers | [Hugging Face](https://github.com/huggingface) | Apache-2.0 |
| rembg / BiRefNet | [rembg](https://github.com/danielgatis/rembg), [BiRefNet](https://github.com/ZhengPeng7/BiRefNet) | MIT |
| MediaPipe FaceLandmarker | [Google MediaPipe](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker) | Apache-2.0; versioned task asset from Google's model endpoint |
| DLP3D audio2face / UniTalker ONNX | [dlp3d-ai/audio2face](https://github.com/dlp3d-ai/audio2face) | MIT source; checkpoint distributed by the linked upstream release |
| AniGen | [VAST-AI-Research/AniGen](https://github.com/VAST-AI-Research/AniGen) | MIT source |
| DSINE normal estimation | [hugoycj/DSINE-hub](https://github.com/hugoycj/DSINE-hub) | DSINE Software Licence: non-commercial internal or academic research |
| DINOv2 | [facebookresearch/dinov2](https://github.com/facebookresearch/dinov2) | Apache-2.0 |
| EfficientNet-PyTorch | [lukemelas/EfficientNet-PyTorch](https://github.com/lukemelas/EfficientNet-PyTorch) | Apache-2.0 |
| PyTorch3D / utils3d / nvdiffrast | Pinned upstreams in `configs/upstreams.lock.json` | BSD-3-Clause / MIT / Nvidia Source Code License (1-Way Commercial) |
| Babylon.js | [BabylonJS](https://github.com/BabylonJS/Babylon.js) | Apache-2.0 |
| PixiJS / pixi-live2d-display | npm lockfile and upstream repositories | MIT |
| Cubism Core / Haru / Hiyori | [Live2D](https://www.live2d.com/), [CubismWebSamples](https://github.com/Live2D/CubismWebSamples) | Live2D Proprietary Software License / Free Material License / Sample Model Terms |
| RobotExpressive | Tomás Laulhé / Quaternius; glTF conversion and facial morphs by Don McCurdy | CC0-1.0 |

DLP3D's rendering reference is MIT, pinned in `configs/upstreams.lock.json`. The audio2face channel order and preprocessing follow DLP3D; its full notice is retained in [licenses/audio2face-MIT.txt](licenses/audio2face-MIT.txt), Copyright (c) 2025 S-Lab, Nanyang Technological University. UniTalker checkpoint-specific licensing is unspecified in that release.

Character packages retain their resource provenance and license files. Live2D's required sample attribution appears in the UI and [resource guide](guides/resources.md). Browser dependency attribution is summarized in [web/THIRD_PARTY.md](web/THIRD_PARTY.md).
