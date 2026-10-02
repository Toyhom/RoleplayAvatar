# Models, hardware and downloads

[English](models.md) · [简体中文](zh-CN/models.md) · [日本語](ja/models.md)

The framework separates model selection from application behavior. Paths choose checkpoints; adapters implement inference; agents select local or hosted endpoints. The [machine-readable catalog](../src/roleplay_avatar/data/models.json) records repository IDs, fixed revisions, adapters, license metadata and approximate inference memory.

## Choose a preset

The following recommendations budget for concurrent dialogue, speech and recognition. Character creation runs separately and loads its models one stage at a time.

| Preset | Suggested hardware | Dialogue | Speech recognition |
| --- | --- | --- | --- |
| Hosted API | Small GPU or remote speech endpoint | Your chosen provider | Configured local/remote ASR |
| `compact` | 1 × 24 GB | Qwen3-4B | Whisper-small |
| `balanced` | 1 × 40–48 GB | Qwen3-8B | Whisper-large-v3-turbo |
| `quality` | 2 × 80 GB | Qwen3-32B | Whisper-large-v3 |
| `showcase` | 3 × 80 GB | CoSER-70B + Qwen3-8B controller | Whisper-large-v3-turbo |

All four local presets use CosyVoice3 for streaming speech. The largest preset distributes actor weights across two GPUs and uses separate allocations for other services. Memory figures include an approximate context/activation allowance and vary with context length, image resolution, batch size and dtype.

```bash
avatar models list
avatar models recommend --vram-gib 48 --gpus 1
avatar models download balanced --model-root /srv/models --dry-run
avatar models download balanced --model-root /srv/models --mirror
avatar models configure balanced --model-root /srv/models --output configs/models.local.json
```

The configure command creates a new file. Set `AVATAR_MODELS_CONFIG` to its absolute path, then restart the affected services. See [Installation](setup.md) for interpreters and service URLs.

## Domestic mirrors and pinned downloads

`--mirror` selects `https://hf-mirror.com`; `--endpoint URL` selects another Hugging Face-compatible mirror. The downloader pins the upstream commit, resumes interrupted files, retains repository documentation and verifies downloaded LFS SHA256 hashes. A receipt is stored as `.avatar-download.json` beside the model.

For a specific model:

```bash
avatar models download qwen3-8b --mirror --model-root /srv/models
avatar models download qwen3-vl-32b --mirror --model-root /srv/models
```

Add `--creation` to a preset for image understanding, illustration and voice design. Quality/showcase choose Qwen3-VL-32B and add Qwen-Image-Edit-2511; set `AVATAR_IMAGE_BACKEND=qwen_image` to use that editor. FLUX remains available for the mouth-reference stage.

Gated repositories use their upstream access flow. Select a credential explicitly with `--token-env HF_TOKEN`. The downloader sends the selected credential to the selected endpoint. A failed download can be resumed by repeating the same command.

The optional downloader dependency is installed with `python -m pip install -e '.[download]'`. `scripts/download_snapshot.py` is an additional range downloader for links that benefit from parallel connections; it accepts a repository, revision and model root and honors `HF_ENDPOINT`.

## Family adapters

`tested` identifies checkpoints with verified inference support. `adapter-compatible` identifies variants supported by the family loader and task interface.

| Module | Family / variants | Adapter and configuration |
| --- | --- | --- |
| Roleplay and text agents | Qwen3 dense 0.6/1.7/4/8/14/32B; MoE 30B-A3B/235B-A22B; CoSER Llama 3.1 8/70B; Transformers causal-LM checkpoints | `services/llm_service.py`, AutoModelForCausalLM; custom chat templates; local, multi-GPU and optional int4/int8 |
| Hosted agents | DeepSeek, Qwen, OpenAI, Claude, compatible model servers | Chat Completions, Responses or Anthropic Messages; per-agent routing |
| Image understanding | Qwen3-VL dense 2/4/8/32B and MoE variants; compatible AutoModelForImageTextToText checkpoints | Auto processor/model; local auto device map, or vision API |
| Image expansion and mouth references | FLUX.2 klein 4B/9B | Flux2KleinPipeline; image-conditioned Diffusers directories |
| Image expansion | Qwen-Image-Edit-2511 and compatible Edit Plus checkpoints | QwenImageEditPlusPipeline; `AVATAR_IMAGE_BACKEND=qwen_image` |
| Voice design | Qwen3-TTS 1.7B VoiceDesign | Natural-language voice creation; this task has one published size in the catalog |
| Streaming speech | CosyVoice3 0.5B | `speech_service.py`, reference-conditioned speech and delivery control |
| Alternative speech | CosyVoice 300M / CosyVoice2 0.5B / CosyVoice3; Qwen3-TTS Base and CustomVoice 0.6/1.7B | `family_speech_service.py`; sentence-buffered output; Base clones a character reference, CustomVoice uses its named speakers |
| Microphone input | Whisper tiny/base/small/medium/large-v3/large-v3-turbo and compatible Whisper checkpoints | `whisper_service.py`; language detection or `--language` |
| Foreground extraction | BiRefNet-general ONNX through rembg | `segmentation` points to the ONNX file |
| Face landmarks | MediaPipe FaceLandmarker | `face_landmarker` points to the `.task` file |
| Audio expressions | UniTalker v0.4.0 base ONNX | Audio-to-face service; channel mapping in `configs/audio-face-names.json` |
| Optional 3D | AniGen, bundled DINOv2 ViT-L/14 registers, DSINE + EfficientNet-B5 | AniGen pipeline and its `dinov2` / `normals` directories |

MoE weight storage follows total parameter count. Active parameters describe compute per token, so a 235B-A22B model still needs storage for its full weights. Fixed-function ONNX/task resources are selected by compatible output contract.

Qwen3-TTS VoiceDesign, Base and CustomVoice perform different jobs. Larger alternatives are chosen within a task-compatible family. [Voice design](voice.md) covers reference creation and speech selection.

## Paths and loader settings

Path precedence:

1. `AVATAR_<ROLE>_MODEL_PATH`.
2. `models.<role>.path` in `AVATAR_MODELS_CONFIG`.
3. `AVATAR_MODEL_ROOT` + configured/default repository and revision.

Paths support `~` and environment variables. Model paths are relative to the process working directory; prompt and chat-template files are relative to the JSON configuration.

Use `repo`, `revision` and `license` to describe your own checkpoints. Download receipts identify catalog snapshots automatically. Creation stages record their actual model identity, and generated packages preserve those stage records when exported or repackaged.

```json
{
  "models": {
    "roleplay": {"path":"/srv/models/my-checkpoint", "device_map":"auto", "dtype":"bfloat16",
                 "context":8192, "quantization":"none", "template_kwargs":{"enable_thinking":false}},
    "vision": {"path":"/srv/models/my-vl-checkpoint"},
    "tts": {"path":"/srv/models/my-cosyvoice"},
    "asr": {"path":"/srv/models/my-whisper"}
  }
}
```

The local LLM loader supports `quantization: "int4" | "int8" | "none"`; int4/int8 require a model environment with a compatible bitsandbytes installation. A served GGUF/AWQ/GPTQ model can instead use the OpenAI-compatible endpoint. Auto placement uses only the GPUs visible to the process; GPUQ supplies that allocation on shared clusters.

Additional registered paths: `image`, `image_edit`, `voice_design`, `voice_clone`, `mesh`, `normals`, `dinov2`, `audio_face`, `segmentation`, `face_landmarker`. Tokenizers, speech encoders, flow/vocoder weights and other bundled components load from their parent model directory. Exact auxiliary asset URLs and hashes are in `configs/*models.lock.json` and `configs/audio-face-model.lock.json`.

## Adding another family

For an existing adapter, add a catalog entry and select its path. For a new architecture, implement the module's [inference contract](architecture.md): text deltas, 24 kHz speech chunks, transcription text, facial coefficients, or creation-stage files. Keep checkpoint-specific imports in the model service environment.

## Per-model memory estimates

Planning estimates in GiB, before adding concurrent services. Dense LLM figures assume 16-bit weights plus context allowance. Image editors may use CPU offload and additional host RAM. Fixed-function face/foreground stages can run on CPU; their host memory depends on image size.

| Module | Catalog ID | VRAM (GiB) | Status |
| --- | --- | --- | --- |
| `asr` | `whisper-base` | 1 | adapter-compatible |
| `asr` | `whisper-tiny` | 1 | adapter-compatible |
| `asr` | `whisper-small` | 2 | tested |
| `asr` | `whisper-large-v3-turbo` | 4 | tested |
| `asr` | `whisper-medium` | 4 | adapter-compatible |
| `asr` | `whisper-large-v3` | 7 | adapter-compatible |
| `image` | `flux2-klein-4b` | 18 | tested |
| `image` | `flux2-klein-9b` | 32 | adapter-compatible |
| `image_edit` | `qwen-image-edit-2511` | 48 | tested |
| `mesh` | `anigen` | 45 | tested |
| `roleplay` | `qwen3-0.6b` | 3 | adapter-compatible |
| `roleplay` | `qwen3-1.7b` | 5 | adapter-compatible |
| `roleplay` | `qwen3-4b` | 10 | adapter-compatible |
| `roleplay` | `coser-8b` | 20 | tested |
| `roleplay` | `qwen3-8b` | 20 | tested |
| `roleplay` | `qwen3-14b` | 34 | adapter-compatible |
| `roleplay` | `qwen3-30b-a3b` | 70 | adapter-compatible |
| `roleplay` | `qwen3-32b` | 74 | adapter-compatible |
| `roleplay` | `coser-70b` | 152 | tested |
| `roleplay` | `qwen3-235b-a22b` | 510 | adapter-compatible |
| `tts` | `cosyvoice1` | 4 | adapter-compatible |
| `tts` | `qwen-tts-0.6b-base` | 4 | adapter-compatible |
| `tts` | `qwen-tts-0.6b-customvoice` | 4 | adapter-compatible |
| `tts` | `cosyvoice2` | 6 | adapter-compatible |
| `tts` | `cosyvoice3` | 6 | tested |
| `tts` | `qwen-tts-1.7b-base` | 8 | tested |
| `tts` | `qwen-tts-1.7b-customvoice` | 8 | adapter-compatible |
| `vision` | `qwen3-vl-2b` | 7 | adapter-compatible |
| `vision` | `qwen3-vl-4b` | 12 | tested |
| `vision` | `qwen3-vl-8b` | 24 | adapter-compatible |
| `vision` | `qwen3-vl-30b-a3b` | 72 | adapter-compatible |
| `vision` | `qwen3-vl-32b` | 76 | tested |
| `vision` | `qwen3-vl-235b-a22b` | 530 | adapter-compatible |
| `voice_design` | `qwen-voice-design` | 8 | tested |

[← All guides](index.md)
