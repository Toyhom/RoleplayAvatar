"""Split legacy dual-mode packages into two independent library characters."""

import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    backup = ROOT / "outputs/migrations/single-presentation"
    backup.mkdir(parents=True, exist_ok=True)
    for folder in sorted((ROOT / "characters").iterdir()):
        if not (folder / "profile.json").is_file():
            continue
        profile = json.loads((folder / "profile.json").read_text())
        if len(profile.get("presentation_modes", ["3d"])) < 2:
            continue
        new_id = "char_" + uuid.uuid4().hex[:16]
        target = ROOT / "characters" / new_id
        data = {
            name: json.loads((folder / (name + ".json")).read_text())
            for name in ["profile", "face_map", "capabilities", "rig_map", "motion_manifest"]
        }
        write(backup / (folder.name + ".json"), {"original": data, "new_2d_id": new_id})
        stage = ROOT / "characters" / (".pending_" + new_id)
        shutil.copytree(folder, stage, ignore=shutil.ignore_patterns("model.glb"))
        p = {
            **profile,
            "character_id": new_id,
            "display_name": profile["display_name"] + " · 2D",
            "model": None,
            "presentation_modes": ["2d"],
        }
        write(stage / "profile.json", p)
        face = {
            "channels": [
                {**c, "renderers": ["2d"]}
                for c in data["face_map"]["channels"]
                if "2d" in c.get("renderers", ["3d"])
            ]
        }
        write(stage / "face_map.json", face)
        caps = {
            **data["capabilities"],
            "face_mode": "blendshape",
            "controller": "humanoid",
            "motion_mode": "procedural",
            "active_streams": ["audio", "motion", "face"],
        }
        write(stage / "capabilities.json", caps)
        rig = {
            **data["rig_map"],
            "root_motion_node": "PortraitRoot",
            "joints": [{"name": "PortraitRoot", "parent": None, "semantic": "root", "owner": "base"}],
        }
        write(stage / "rig_map.json", rig)
        plan = json.loads((stage / "character.json").read_text())
        plan["display_name"] = p["display_name"]
        write(stage / "character.json", plan)
        provenance = json.loads((stage / "provenance.json").read_text())
        provenance["notes"] += " Split 2D package from " + folder.name + "."
        write(stage / "provenance.json", provenance)
        stage.rename(target)
        profile["presentation_modes"] = ["3d"]
        profile["display_name"] += " · 3D"
        face = {
            "channels": [
                {**c, "renderers": ["3d"]}
                for c in data["face_map"]["channels"]
                if "3d" in c.get("renderers", ["3d"])
            ]
        }
        caps = data["capabilities"]
        if not face["channels"]:
            caps["face_mode"] = "none"
            caps["active_streams"] = ["audio", "motion"]
        write(folder / "face_map.json", face)
        write(folder / "capabilities.json", caps)
        write(folder / "profile.json", profile)
        print("SPLIT", folder.name, new_id)


if __name__ == "__main__":
    main()
