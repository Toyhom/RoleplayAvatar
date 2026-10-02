"""Render the actual generated surface and skeleton for vision-guided rig mapping."""

import io
import json
from pathlib import Path

import numpy as np
import nvdiffrast.torch as dr
import torch
from glb_geometry import joint_world_positions, read_accessor
from PIL import Image, ImageDraw
from pygltflib import GLTF2


def render(folder):
    folder = Path(folder)
    glb = GLTF2().load(str(folder / "model.glb"))
    primitive = glb.meshes[0].primitives[0]
    vertices = read_accessor(glb, primitive.attributes.POSITION)
    indices = read_accessor(glb, primitive.indices).reshape(-1, 3)
    uv = read_accessor(glb, primitive.attributes.TEXCOORD_0)
    material = glb.materials[primitive.material]
    texture = glb.textures[material.pbrMetallicRoughness.baseColorTexture.index]
    bv = glb.bufferViews[glb.images[texture.source].bufferView]
    raw = glb.binary_blob()[bv.byteOffset : bv.byteOffset + bv.byteLength]
    texture_np = np.array(Image.open(io.BytesIO(raw)).convert("RGB")) / 255.0
    center = (vertices.min(0) + vertices.max(0)) / 2
    extent = max(float(np.ptp(vertices[:, 0])), float(np.ptp(vertices[:, 1]))) * 1.14
    ctx = dr.RasterizeCudaContext()
    tri = torch.as_tensor(indices.astype(np.int32), device="cuda")
    tex = torch.as_tensor(texture_np.astype(np.float32), device="cuda")[None]
    texcoord = torch.as_tensor(uv.astype(np.float32), device="cuda")[None]
    joints = joint_world_positions(glb)
    report = {"center": center.tolist(), "extent": extent, "views": []}
    for sign, name in [(1, "front"), (-1, "back")]:
        clip = np.ones((len(vertices), 4), np.float32)
        clip[:, :3] = (vertices - center) / extent * 2
        clip[:, 0] *= sign
        clip[:, 2] *= -sign * 0.5
        rast, _ = dr.rasterize(ctx, torch.as_tensor(clip, device="cuda")[None], tri, resolution=(768, 768))
        interp, _ = dr.interpolate(texcoord, rast, tri)
        # glTF UV origin is upper-left; nvdiffrast texture tensor rows follow the image here.
        color = dr.texture(tex, interp, filter_mode="linear", boundary_mode="clamp")
        bg = torch.tensor([0.89, 0.9, 0.88], device="cuda")
        color = torch.where(rast[..., 3:4] > 0, color, bg)
        image = Image.fromarray((color[0].flip(0).clamp(0, 1).cpu().numpy() * 255).astype(np.uint8))
        image.save(folder / f"mesh-{name}.png")
        overlay = image.copy()
        draw = ImageDraw.Draw(overlay)
        projected = {}
        for i, p in joints.items():
            x = (0.5 + sign * (p[0] - center[0]) / extent) * 768
            y = (0.5 - (p[1] - center[1]) / extent) * 768
            projected[glb.nodes[i].name] = [round(x / 768, 4), round(y / 768, 4)]
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill="#ed602c")
            draw.text((x + 3, y - 7), str(i - 1), fill="#cc2912", stroke_width=1, stroke_fill="white")
        overlay.save(folder / f"rig-{name}.png")
        report["views"].append({"name": name, "sign": sign, "joints": projected})
    (folder / "projection.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    import sys

    render(Path(sys.argv[1]))
