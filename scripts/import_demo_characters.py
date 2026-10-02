"""Publish downloaded native sample packages with generated voices and provenance."""

import argparse
import json
import shutil
import struct
from pathlib import Path

from roleplay_avatar.assets import load_package
from roleplay_avatar.contracts import STATES
from roleplay_avatar.creation import write_json
from roleplay_avatar.import_assets import normalize_skin_weights

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/demo-imports"
NOTICE = (
    "This content uses sample data owned and copyrighted by Live2D Inc. "
    "The sample data are utilized in accordance with terms and conditions set by Live2D Inc. "
    "This content itself is created at the author’s sole discretion."
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace", action="store_true", help="Reimport these sample packages from the pinned downloads"
    )
    args = parser.parse_args()
    config = json.loads((ROOT / "configs/demo-assets.json").read_text())
    downloads = json.loads((OUT / "downloads.json").read_text())
    for item in config["characters"]:
        cid = item["id"]
        src = OUT / cid
        target = ROOT / "characters" / cid
        if target.exists() and not args.replace:
            load_package(target, require_assets=True)
            print("ALREADY_IMPORTED", cid)
            continue
        package = OUT / (".package-" + cid)
        package.mkdir(exist_ok=True)
        shutil.copytree(src / "voice", package / "voice", dirs_exist_ok=True)
        voices = json.loads((src / "voice/candidates.json").read_text())
        selected = next(v for v in voices["candidates"] if v["candidate"] == voices["selected"])
        is2d = item["mode"] == "2d"
        version = "native-" + item["asset"] + "-v1"
        profile = {
            "character_id": cid,
            "display_name": item["name"],
            "persona": item["persona"],
            "package_status": "validated",
            "model": None if is2d else "model.glb",
            "presentation_modes": [item["mode"]],
        }
        repairs = []
        sources = []
        issues = []
        if is2d:
            shutil.copytree(src / "live2d", package / "live2d", dirs_exist_ok=True)
            shutil.copytree(OUT / "licenses", package / "licenses", dirs_exist_ok=True)
            (package / "licenses/NOTICE.txt").write_text(NOTICE + "\n")
            profile.update(renderer_2d="cubism", live2d_model=f"live2d/{item['asset']}.model3.json")
            targets = {
                name: name
                for name in [
                    "jaw_open",
                    "happy",
                    "sad",
                    "angry",
                    "soft",
                    "mouth_round",
                    "mouth_wide",
                    "brow_up",
                    "eye_squint",
                ]
            }
            sources = [
                {
                    "component": "model",
                    "source": "https://github.com/Live2D/CubismWebSamples",
                    "revision": config["cubism_revision"],
                    "license": "Live2D Free Material License + Sample Model Terms",
                    "attribution": NOTICE,
                    "terms": "https://www.live2d.com/eula/live2d-sample-model-terms_en.html",
                }
            ]
            issues = [
                "Original Live2D artwork and rig; dialogue persona and synthetic voice are created by the framework.",
                "Live2D Core and model assets retain separate terms. Corporate external promotion/release may require additional permission.",
            ]
        else:
            shutil.copyfile(src / "model.glb", package / "model.glb")
            shutil.copytree(src / "licenses", package / "licenses", dirs_exist_ok=True)
            repairs.append(normalize_skin_weights(package / "model.glb"))
            raw = (package / "model.glb").read_bytes()
            size = struct.unpack_from("<I", raw, 12)[0]
            gltf = json.loads(raw[20 : 20 + size])
            names = {a["name"] for a in gltf["animations"]}
            assert {"Idle", "Yes", "No", "Dance", "Jump", "Wave", "ThumbsUp"} <= names
            targets = {"jaw_open": "Surprised", "sad": "Sad", "angry": "Angry"}
            profile.update(
                display_rotation_y_deg=180,
                native_animation_map={
                    "nod": "Yes",
                    "shake_head": "No",
                    "sway": "Dance",
                    "bounce": "Jump",
                    "lean_forward": "ThumbsUp",
                },
            )
            sources = [
                {
                    "component": "model",
                    "source": "https://github.com/mrdoob/three.js/tree/"
                    + config["three_revision"]
                    + "/examples/models/gltf/RobotExpressive",
                    "revision": config["three_revision"],
                    "license": "CC0-1.0",
                    "attribution": "Tomás Laulhé / Quaternius; glTF conversion and facial morphs by Don McCurdy.",
                }
            ]
            issues = [
                "Robot mouth uses the original Surprised morph. It does not contain human visemes or detailed tongue/teeth articulation."
            ]
        records = {
            "profile": profile,
            "capabilities": {
                "body_topology": "humanoid",
                "face_mode": "blendshape",
                "eye_mode": "paired" if is2d else "none",
                "controller": "humanoid",
                "motion_mode": "native_clips",
                "active_streams": ["audio", "motion", "face"],
            },
            "rig_map": {
                "skeleton_version": version,
                "coordinate_system": "right_handed_y_up_meters",
                "root_motion_node": "PresentationRoot" if is2d else "RootNode",
                "joints": [
                    {
                        "name": "PresentationRoot" if is2d else "RootNode",
                        "parent": None,
                        "semantic": "root",
                        "owner": "base",
                    }
                ],
            },
            "face_map": {
                "channels": [
                    {"source": source, "target": name, "renderers": [item["mode"]]}
                    for source, name in targets.items()
                ]
            },
            "motion_manifest": {
                "skeleton_version": version,
                "motions": {
                    name: {
                        "procedural": "neutral"
                        if name in {"idle", "long_idle", "listen", "think", "error"}
                        else "speech_rhythm"
                    }
                    for name in sorted(STATES)
                },
            },
            "voice_profile": {
                "backend": "cosyvoice3",
                "model_id": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
                "revision": "29e01c4e8d000f4bcd70751be16fa94bf3d85a18",
                "reference_audio": f"voice/candidate_{voices['selected']}.wav",
                "reference_text": "voice/reference.txt",
                "reference_sha256": selected["sha256"],
                "supported_styles": ["neutral", "happy", "sad", "angry", "soft"],
                "design_prompt": selected["prompt"],
            },
            "provenance": {
                "kind": "external_asset",
                "sources": sources
                + [
                    {
                        "component": "voice",
                        "source": voices["model"],
                        "license": "Apache-2.0",
                        "note": "New synthetic demo voice, not original character audio",
                    }
                ],
                "generation_record": "generation.json",
                "notes": "Imported native demonstration asset. "
                + ("Hiyori design unchanged. " if item["asset"] == "Hiyori" else "")
                + ("Live2D sample and Core terms apply." if is2d else "CC0 visual asset."),
            },
            "qa_report": {
                "status": "passed",
                "checks": {"manifest": "passed", "voice_integrity": "passed", "source_downloads": "passed"},
                "known_issues": issues,
            },
            "character": {
                "display_name": item["name"],
                "persona": item["persona"],
                "tagline": "官方原生 Live2D 示例" if is2d else "CC0 原生动画机器人",
                "voice_design": item["voice_design"],
            },
            "generation": {
                "kind": "external_import",
                "asset": item["asset"],
                "downloads": [r for r in downloads if "/" + cid + "/" in r["file"]],
                "voice": {
                    "backend": "Qwen3-TTS VoiceDesign",
                    "seeds": [v["seed"] for v in voices["candidates"]],
                },
                "automatic_generation_claim": False,
                "asset_repairs": repairs,
            },
        }
        for name, value in records.items():
            write_json(package / (name + ".json"), value)
        load_package(package, require_assets=True)
        if target.exists():
            shutil.copytree(package, target, dirs_exist_ok=True)
            shutil.rmtree(package)
        else:
            package.rename(target)
        print("IMPORTED", cid, flush=True)


if __name__ == "__main__":
    main()
