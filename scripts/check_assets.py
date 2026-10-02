"""Inspect the actual GLB buffers, named control channels and fixed voice hashes."""

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

from roleplay_avatar.assets import catalog, cubism_files, load_package

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--characters", nargs="+", help="Character IDs; default: the whole local library")
parser.add_argument("--output", type=Path, default=root / "outputs/asset-validation/report.json")
args = parser.parse_args()
reports = []
library = catalog(root / "characters")
for cid in args.characters or library:
    character = load_package(root / "characters" / cid, require_assets=True)
    folder = root / "characters" / cid
    doc = None
    if character.profile.model:
        raw = (folder / character.profile.model).read_bytes()
        assert struct.unpack_from("<III", raw) == (0x46546C67, 2, len(raw))
        length, kind = struct.unpack_from("<II", raw, 12)
        assert kind == 0x4E4F534A
        doc = json.loads(raw[20 : 20 + length])
        binary_length, kind = struct.unpack_from("<II", raw, 20 + length)
        assert kind == 0x004E4942
        binary = raw[28 + length : 28 + length + binary_length]
        skins = doc.get("skins", [])
        bone_names = {doc["nodes"][i]["name"] for skin in skins for i in skin["joints"]}
        # Importers may drive a scene root above multiple independent skins.
        control_names = {node.get("name") for node in doc["nodes"]}
        assert all(joint.name in control_names for joint in character.rig_map.joints)
        assert character.rig_map.root_motion_node in control_names
        morphs = {n for mesh in doc["meshes"] for n in mesh.get("extras", {}).get("targetNames", [])}
        assert all(
            channel.target in morphs for channel in character.face_map.channels if "3d" in channel.renderers
        )
        assert set(character.profile.native_animation_map.values()) <= {
            a["name"] for a in doc.get("animations", [])
        }
    if character.profile.renderer_2d == "cubism":
        declared = cubism_files(folder, character.profile.live2d_model)
        assert all((folder / name).is_file() for name in declared)
        manifest = json.loads((folder / character.profile.live2d_model).read_text())
        assert manifest["FileReferences"]["Textures"] and manifest["FileReferences"]["Motions"]
        moc = folder / "live2d" / manifest["FileReferences"]["Moc"]
        assert moc.read_bytes()[:4] == b"MOC3"
    elif "2d" in character.profile.presentation_modes:
        puppet = json.loads((folder / "puppet/rig.json").read_text())
        assert (folder / "puppet/portrait.png").is_file()
        assert all(c.target in puppet["channels"] for c in character.face_map.channels if "2d" in c.renderers)
    vertices = 0
    if doc:
        for mesh in doc["meshes"]:
            for primitive in mesh["primitives"]:
                attributes = primitive["attributes"]
                if "WEIGHTS_0" not in attributes:
                    continue
                acc = doc["accessors"][attributes["WEIGHTS_0"]]
                assert acc["type"] == "VEC4" and acc["componentType"] == 5126 and "sparse" not in acc
                view = doc["bufferViews"][acc["bufferView"]]
                start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
                stride = view.get("byteStride", 16)
                for i in range(acc["count"]):
                    weights = struct.unpack_from("<4f", binary, start + i * stride)
                    assert all(math.isfinite(v) and 0 <= v <= 1 for v in weights)
                    assert abs(sum(weights) - 1) < 0.001
                vertices += acc["count"]
        if skins:
            assert vertices > 0
    sha = hashlib.sha256((folder / character.voice_profile.reference_audio).read_bytes()).hexdigest()
    assert sha == character.voice_profile.reference_sha256
    reports.append(
        {
            "character": cid,
            "format": "GLB2" if doc else character.profile.renderer_2d,
            "bytes": len(raw) if doc else None,
            "model_sha256": hashlib.sha256(raw).hexdigest() if doc else None,
            "skeletons": len(doc.get("skins", [])) if doc else 0,
            "skin_joints": len(bone_names) if doc else 0,
            "meshes": len(doc["meshes"]) if doc else 0,
            "animations": [a["name"] for a in doc.get("animations", [])] if doc else [],
            "voice_sha256": sha,
            "normalized_skinned_vertices": vertices,
        }
    )
output = args.output
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(reports, indent=2, ensure_ascii=False) + "\n")
print("ASSET_STRUCTURE_PASS", len(reports))
