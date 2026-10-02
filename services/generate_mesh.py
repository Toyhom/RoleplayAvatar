"""Run pinned AniGen inference without changing the upstream checkout."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--model", type=Path, required=True)
parser.add_argument("--job", type=Path, required=True)
args = parser.parse_args()
work = args.job / "anigen-work"
work.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "src"))
from roleplay_avatar.models import model_path

links = {"extensions/DSINE-hub": ROOT / "third_party/dsine-src"}
for item in (args.model / "ckpts").iterdir():
    links["ckpts/" + item.name] = item
for name, role in [("dsine", "normals"), ("dinov2", "dinov2")]:
    from roleplay_avatar.models import configuration

    if os.environ.get("AVATAR_" + role.upper() + "_MODEL_PATH") or configuration().get("models", {}).get(
        role, {}
    ).get("path"):
        links["ckpts/" + name] = model_path(role, check=True)
for name, target in links.items():
    link = work / name
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(target, target_is_directory=True)
os.chdir(work)
sys.path.insert(0, str(ROOT / "third_party/anigen"))
# Matting uses its CPU/ONNX path; inherited CuPy targets a different NumPy ABI.
sys.modules["cupy"] = None
os.environ["ATTN_BACKEND"] = "sdpa"
os.environ["SPARSE_ATTN_BACKEND"] = "flash_attn"
import numpy as np
import torch
from anigen.pipelines import AnigenImageTo3DPipeline
from PIL import Image

renderer = os.environ.get("AVATAR_MESH_RENDERER", "color")
if renderer == "color":
    from anigen_render import install

    install(args.job)
elif renderer != "upstream":
    raise ValueError("Unknown mesh renderer")

# DSINE's EfficientNet initializer reads Torch Hub's checkpoint cache.
# Point that cache entry at the pinned shared snapshot rather than downloading another copy.
torch.hub.set_dir(str(work / "torch-hub"))
checkpoint = Path(torch.hub.get_dir()) / "checkpoints/tf_efficientnet_b5_ap-9e82fae8.pth"
checkpoint.parent.mkdir(parents=True, exist_ok=True)
if not checkpoint.exists():
    checkpoint.symlink_to(links["ckpts/dsine"] / "tf_efficientnet_b5_ap-9e82fae8.pth")

request = json.loads((args.job / "request.json").read_text())
pipe = AnigenImageTo3DPipeline.from_pretrained(
    ss_flow_path="ckpts/anigen/ss_flow_duet", slat_flow_path="ckpts/anigen/slat_flow_auto", device="cuda"
)
# AniGen enables gradients locally to optimize its texture atlas. Inference mode
# would prevent that even inside torch.enable_grad(); no_grad is nestable.
with torch.no_grad():
    result = pipe.run(
        Image.open(args.job / "concept.png"),
        seed=request["seed"],
        ss_steps=25,
        slat_steps=25,
        texture_size=1024,
        simplify_ratio=0.9,
        output_glb=str(args.job / "model.glb"),
    )
result["processed_image"].save(args.job / "processed.png")
np.savez_compressed(
    args.job / "skeleton.npz",
    joints=result["joints"],
    parents=result["parents"],
    vertices=np.asarray(result["mesh"].vertices),
    skin_weights=result["skin_weights"],
)
from render_generated import render

render(args.job)
(args.job / "mesh-generation.json").write_text(
    json.dumps(
        {
            "model": "VAST-AI/AniGen",
            "seed": request["seed"],
            "ss_steps": 25,
            "slat_steps": 25,
            "texture_size": 1024,
            "simplify_ratio": 0.9,
            "renderer": renderer,
        },
        indent=2,
    )
)
print("RIGGED_MESH_READY", flush=True)
