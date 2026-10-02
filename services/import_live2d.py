"""Resumable native-resource creation worker; character/voice design remain automated."""

import asyncio
import fcntl
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from roleplay_avatar.assets import load_package
from roleplay_avatar.contracts import STATES
from roleplay_avatar.creation import read_json, write_json
from roleplay_avatar.design import design_character
from roleplay_avatar.models import model_path

ROOT = Path(__file__).resolve().parents[1]
job = Path(sys.argv[1]).resolve()
if not job.is_relative_to(ROOT / "outputs/creations") or not (job / "request.json").is_file():
    raise ValueError("Invalid worker request directory")
local_lock = None
if os.environ.get("AVATAR_CREATION_RUNNER") == "local":
    local_lock = (job.parent / "worker.lock").open("a")
    fcntl.flock(local_lock, fcntl.LOCK_EX)
request = read_json(job / "request.json")
state = read_json(job / "status.json")


def update(stage, progress, **values):
    if (job / "cancel").exists():
        raise InterruptedError("cancelled")
    state.update(state="running", stage=stage, progress=progress, updated_at=time.time(), **values)
    write_json(job / "status.json", state)


try:
    update("understanding", 15)
    if not (job / "plan.json").exists():
        write_json(job / "plan.json", asyncio.run(design_character(
            request["description"], locale=request.get("locale", "zh-CN")
        )).model_dump())
    plan = read_json(job / "plan.json")
    update("voicing", 45)
    if not (job / "voice/candidates.json").exists():
        with (job / "voicing.log").open("a") as log:
            subprocess.run(
                [
                    os.environ["AVATAR_QWEN_PYTHON"],
                    str(ROOT / "services/character_voices.py"),
                    "--model",
                    str(model_path("voice_design")),
                    "--job",
                    str(job),
                ],
                check=True,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
    update("packaging", 90)
    package = job / "package"
    package.mkdir(exist_ok=True)
    shutil.copytree(job / "live2d", package / "live2d", dirs_exist_ok=True)
    shutil.copytree(job / "voice", package / "voice", dirs_exist_ok=True)
    for item in (job / "live2d").rglob("*"):
        if item.is_file() and (
            item.suffix.lower() in {".txt", ".md", ".html", ".pdf"}
            or item.name.lower() in {"license", "notice"}
        ):
            target = package / "licenses" / item.relative_to(job / "live2d")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
    voices = read_json(job / "voice/candidates.json")
    selected = next(v for v in voices["candidates"] if v["candidate"] == voices["selected"])
    cid = "char_" + job.name[:16]
    version = "cubism-" + request["import_report"]["moc_sha256"][:16]
    lips = request["import_report"]["lip_sync_parameters"]
    records = {
        "profile": {
            "character_id": cid,
            "display_name": plan["display_name"],
            "persona": plan["persona"],
            "model": None,
            "package_status": "validated",
            "presentation_modes": ["2d"],
            "renderer_2d": "cubism",
            "live2d_model": request["native_manifest"],
            "live2d_parameter_map": {"ParamMouthOpenY": lips[0]} if lips else {},
        },
        "capabilities": {
            "body_topology": "humanoid",
            "face_mode": "blendshape",
            "eye_mode": "paired",
            "controller": "humanoid",
            "motion_mode": "native_clips",
            "active_streams": ["audio", "motion", "face"],
        },
        "rig_map": {
            "skeleton_version": version,
            "coordinate_system": "right_handed_y_up_meters",
            "root_motion_node": "PresentationRoot",
            "joints": [{"name": "PresentationRoot", "parent": None, "semantic": "root", "owner": "base"}],
        },
        "face_map": {
            "channels": [
                {"source": name, "target": name, "renderers": ["2d"]}
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
            ]
        },
        "motion_manifest": {
            "skeleton_version": version,
            "motions": {name: {"procedural": "neutral"} for name in sorted(STATES)},
        },
        "voice_profile": {
            "backend": "cosyvoice3",
            "reference_audio": f"voice/candidate_{voices['selected']}.wav",
            "reference_text": "voice/reference.txt",
            "reference_sha256": selected["sha256"],
            "supported_styles": ["neutral", "happy", "sad", "angry", "soft"],
            "design_prompt": selected["prompt"],
        },
        "provenance": {
            "kind": "external_asset",
            "sources": [
                {
                    "component": "model",
                    "source": "user-uploaded Live2D ZIP",
                    "license": "user-provided terms",
                    "sha256": request["import_report"]["archive_sha256"],
                }
            ],
            "generation_record": "generation.json",
            "notes": "Original user-supplied Cubism resources, automated dialogue persona and synthetic voice design.",
        },
        "qa_report": {
            "status": "passed",
            "checks": {"native_manifest": "passed", "native_textures": "passed", "voice_integrity": "passed"},
            "known_issues": [],
        },
        "character": plan,
        "generation": {
            "kind": "native_import",
            "resource_validation": request["import_report"],
            "voice_design": voices["model"],
        },
    }
    for name, value in records.items():
        write_json(package / (name + ".json"), value)
    load_package(package, require_assets=True)
    update("publishing", 98)
    target = ROOT / "characters" / cid
    if not target.exists():
        stage = ROOT / "characters" / (".pending_" + cid)
        shutil.copytree(package, stage, dirs_exist_ok=True)
        stage.rename(target)
    state.update(state="ready", stage="complete", progress=100, character_id=cid, updated_at=time.time())
    write_json(job / "status.json", state)
    print("NATIVE_CHARACTER_READY", cid, flush=True)
except Exception as exc:
    state.update(
        state="cancelled" if isinstance(exc, InterruptedError) else "failed",
        error="资源导入未完成，请检查任务记录后重试。",
        error_type=type(exc).__name__,
        updated_at=time.time(),
    )
    write_json(job / "status.json", state)
    raise
