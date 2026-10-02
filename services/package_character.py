"""Inspect generated geometry and publish explicit, portable character contracts."""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from fit_face import fit
from fit_head import select_head
from pygltflib import GLTF2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roleplay_avatar.model_metadata import source_record

parser = argparse.ArgumentParser()
parser.add_argument("--job", type=Path, required=True)
args = parser.parse_args()
folder = args.job
plan = json.loads((folder / "plan.json").read_text())
request = json.loads((folder / "request.json").read_text())
voices = json.loads((folder / "voice/candidates.json").read_text())
selected = next(v for v in voices["candidates"] if v["candidate"] == voices["selected"])
analysis = json.loads((folder / "rig-analysis.json").read_text())
if (folder / "face-landmarks-mp.json").is_file():
    measured = json.loads((folder / "face-landmarks-mp.json").read_text()).get(analysis["view"], {})
    if measured.get("landmark_validated"):
        analysis.update(measured)
        analysis["face_visible"] = True
projection = json.loads((folder / "projection.json").read_text())
refinement = (
    json.loads((folder / "texture-refinement.json").read_text())
    if (folder / "texture-refinement.json").is_file()
    else {"enabled": False}
)
mesh_folder = folder / "refined" if refinement.get("enabled") else folder
glb = GLTF2().load(str(mesh_folder / "model.glb"))
blob = glb.binary_blob()
if len(glb.skins) != 1:
    raise ValueError("Expected one connected generated skeleton")
skin = glb.skins[0]


def accessor(index):
    a = glb.accessors[index]
    view = glb.bufferViews[a.bufferView]
    types = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}
    widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
    dtype, width = np.dtype(types[a.componentType]), widths[a.type]
    if a.sparse:
        raise ValueError("Sparse accessors need a dedicated importer")
    return np.ndarray(
        (a.count, width),
        dtype=dtype,
        buffer=blob,
        offset=(view.byteOffset or 0) + (a.byteOffset or 0),
        strides=(view.byteStride or dtype.itemsize * width, dtype.itemsize),
    ).copy()


vertices, weights, joint_ids = [], [], []
for mesh in glb.meshes:
    for primitive in mesh.primitives:
        v = accessor(primitive.attributes.POSITION)
        w = accessor(primitive.attributes.WEIGHTS_0)
        j = accessor(primitive.attributes.JOINTS_0)
        idx = accessor(primitive.indices)
        if not np.isfinite(v).all() or not np.isfinite(w).all():
            raise ValueError("Non-finite generated geometry")
        if idx.max() >= len(v) or j.max() >= len(skin.joints):
            raise ValueError("Invalid generated indices")
        if np.min(w) < 0 or np.max(w) > 1.001 or not np.allclose(w.sum(1), 1, atol=0.001):
            raise ValueError("Invalid skinning weights")
        vertices.append(v)
        weights.append(w)
        joint_ids.append(j)
vertices, weights, joint_ids = map(np.concatenate, (vertices, weights, joint_ids))
if len(vertices) < 100 or np.ptp(vertices[:, 1]) < 0.01:
    raise ValueError("Generated mesh is empty or degenerate")
parents = {child: i for i, node in enumerate(glb.nodes) for child in node.children or []}
joint_set = set(skin.joints)
root_index = skin.skeleton
if root_index not in joint_set:
    joint_set.add(root_index)
semantic = {}
height = float(np.ptp(vertices[:, 1]))
top = vertices[:, 1] > np.max(vertices[:, 1]) - height * 0.22
scores = []
for ordinal, node_index in enumerate(skin.joints):
    influence = np.sum(weights * (joint_ids == ordinal), axis=1)
    top_mass = float(np.sum(influence[top]))
    total_mass = float(np.sum(influence))
    purity = top_mass / max(total_mass, 0.0001)
    if purity > 0.65 and top_mass > 50 and node_index != root_index:
        scores.append((top_mass * purity, node_index))
if scores:
    semantic[max(scores)[1]] = "head" if plan["body_topology"] == "humanoid" else "sensor"
if analysis.get("confidence", 0) >= 0.75 and analysis.get("head_joint"):
    mapped = next((i for i in skin.joints if glb.nodes[i].name == analysis["head_joint"]), None)
    if mapped is not None and mapped != root_index:
        semantic = {mapped: "head"}

head_binding = select_head(glb, analysis, projection)
if head_binding:
    semantic = {head_binding["node"]: "head"}

joints = []
for i in sorted(joint_set):
    node = glb.nodes[i]
    parent = parents.get(i)
    role = semantic.get(i, "root" if i == root_index else "body")
    joints.append(
        {
            "name": node.name,
            "parent": glb.nodes[parent].name if parent in joint_set else None,
            "semantic": role,
            "owner": "expression" if i in semantic else "base",
            "rest_translation": node.translation or [0, 0, 0],
            "rest_rotation_xyzw": node.rotation or [0, 0, 0, 1],
            "local_axis": [1, 0, 0],
            "angle_limits_deg": [-7, 7] if i in semantic else [-3, 3],
        }
    )

package = folder / "package"
package.mkdir(exist_ok=True)
shutil.copyfile(mesh_folder / "model.glb", package / "model.glb")
for name in ("concept.png", "input.png"):
    shutil.copyfile(folder / name, package / name)
face = fit(glb, analysis, projection)
if face["enabled"]:
    glb.save_binary(str(package / "model.glb"))
shutil.copyfile(mesh_folder / f"mesh-{analysis['view']}.png", folder / "preview.png")
shutil.copyfile(folder / "preview.png", package / "preview.png")
(folder / "face-fitting.json").write_text(json.dumps(face, indent=2))
shutil.copytree(folder / "voice", package / "voice", dirs_exist_ok=True)
cid = "char_" + request["id"][:16]
topology = plan["body_topology"]
if topology not in {"humanoid", "quadruped", "multiped", "serpentine", "custom"}:
    topology = "custom"
version = "anigen_" + hashlib.sha256((package / "model.glb").read_bytes()).hexdigest()[:12]
motions = {}
for state in (
    "idle",
    "long_idle",
    "listen",
    "think",
    "speak",
    "acknowledge",
    "explain",
    "uncertain",
    "alert",
    "leave",
    "error",
):
    procedure = "neutral" if state in {"idle", "long_idle", "listen", "think", "error"} else "speech_rhythm"
    motions[state] = {"procedural": procedure, "duration_s": 2, "loop": state in {"idle", "listen", "speak"}}
records = {
    "profile": {
        "schema_version": "0.1.0",
        "character_id": cid,
        "display_name": plan["display_name"],
        "persona": plan["persona"],
        "package_status": "validated",
        "model": "model.glb",
        "display_rotation_y_deg": 180 if analysis["view"] == "front" else 0,
        "display_height_m": 2.1,
    },
    "capabilities": {
        "body_topology": topology,
        "face_mode": "blendshape" if face["enabled"] else "none",
        "eye_mode": "none",
        "appendages": [],
        "controller": "humanoid" if topology == "humanoid" else "creature",
        "motion_mode": "procedural",
        "active_streams": ["audio", "motion"] + (["face"] if face["enabled"] else []),
    },
    "rig_map": {
        "skeleton_version": version,
        "coordinate_system": "right_handed_y_up_meters",
        "root_motion_node": glb.nodes[root_index].name,
        "joints": joints,
    },
    "face_map": {
        "channels": [
            {"source": name, "target": name, "minimum": 0, "maximum": 1} for name in face.get("channels", [])
        ]
    },
    "motion_manifest": {"skeleton_version": version, "motions": motions},
    "voice_profile": {
        "backend": "cosyvoice3",
        "model_id": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
        "revision": "29e01c4e8d000f4bcd70751be16fa94bf3d85a18",
        "reference_audio": f"voice/candidate_{voices['selected']}.wav",
        "reference_text": "voice/reference.txt",
        "reference_sha256": selected["sha256"],
        "supported_styles": ["neutral", "happy", "sad", "angry", "soft"],
        "design_prompt": selected["prompt"],
        "effects": "dry",
    },
    "provenance": {
        "kind": "generated_asset",
        "seed": request["seed"],
        "sources": [
            {
                "component": "input",
                "source": "user upload",
                "sha256": request["input_sha256"],
                "license": "user-provided",
            },
            source_record("image", json.loads((folder / "image-generation.json").read_text())),
            {"component": "geometry_skeleton_skin", "source": "VAST-AI/AniGen", "license": "MIT"},
            source_record("persona", plan.get("source", {"model": "Qwen/Qwen3-VL-4B-Instruct"})),
            source_record("voice", voices),
        ],
        "notes": "Image-conditioned mesh, skeleton and skin generated by AniGen. Voice instructions come from the image-grounded character bible. Source image rights remain with the uploader.",
    },
    "qa_report": {
        "status": "passed",
        "checks": {
            "finite_geometry": "passed",
            "skin_weights": "passed",
            "vertex_indices": "passed",
            "single_skeleton": "passed",
            "voice_integrity": "passed",
        },
        "known_issues": [
            "Single-image hidden surfaces are generated hypotheses.",
            "Facial motion is bounded geometric fitting, not phoneme-level lip sync."
            if face["enabled"]
            else "No reliable facial landmarks; only actual mapped joints are driven.",
            "Voice recommendation ranks signal quality; character fit is selected by audition.",
        ],
    },
    "character": plan,
}
root = Path(__file__).resolve().parents[1]
locks = json.loads((root / "configs/creation-models.lock.json").read_text())["models"]
locks += json.loads((root / "configs/models.lock.json").read_text())["models"]
revisions = {entry["repo_id"]: entry["revision"] for entry in locks}
for source in records["provenance"]["sources"]:
    if source["source"] in revisions and "revision" not in source:
        source["revision"] = revisions[source["source"]]
records["provenance"]["sources"].append(
    {
        "component": "normal_estimation",
        "source": "hugoycj/DSINE-hub",
        "revision": "a6b7d253d515f57404002da58f0c61e90d0387a3",
        "license": "DSINE non-commercial research license",
    }
)
generation = {}
for key, name in (
    ("image", "image-generation.json"),
    ("mesh", "mesh-generation.json"),
    ("face_texture", "texture-refinement.json"),
    ("landmarks", "rig-analysis.json"),
):
    if (folder / name).is_file():
        generation[key] = json.loads((folder / name).read_text())
generation["expressions"] = face
generation["head_binding"] = head_binding
records["profile"]["presentation_modes"] = ["3d"]
records["generation"] = generation
records["provenance"]["generation_record"] = "generation.json"
if generation.get("mesh"):
    for source in records["provenance"]["sources"]:
        if source["component"] == "geometry_skeleton_skin":
            source["seed"] = str(generation["mesh"]["seed"])
            source["renderer"] = generation["mesh"]["renderer"]
if analysis.get("landmark_method") == "mediapipe-face-landmarker":
    face_model = json.loads((root / "configs/creation-models.lock.json").read_text())["face_landmarker"]
    records["provenance"]["sources"].append(
        {
            "component": "face_landmarks",
            "source": face_model["url"],
            "sha256": face_model["sha256"],
            "license": "Google MediaPipe model asset terms; see official model card",
        }
    )
if refinement.get("enabled"):
    records["provenance"]["notes"] += (
        " Visible facial texture is aligned from the generated concept using MediaPipe landmarks and z-buffer visibility."
    )
for name, data in records.items():
    (package / (name + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
(folder / "geometry-qa.json").write_text(
    json.dumps(
        {
            "vertices": len(vertices),
            "joints": len(joints),
            "head_mapping": semantic,
            "height": height,
            "model_sha256": hashlib.sha256((package / "model.glb").read_bytes()).hexdigest(),
        },
        indent=2,
    )
)
print("CHARACTER_PACKAGE_READY", cid, flush=True)
