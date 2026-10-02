"""Transfer visible facial detail from the generated concept onto its generated mesh.

Uses detected landmark correspondence, existing UVs and z-buffer visibility.
The back and occluded surfaces retain AniGen's generated texture.
"""

import argparse
import io
import json
from pathlib import Path

import cv2
import numpy as np
import nvdiffrast.torch as dr
import torch
import torch.nn.functional as F
from glb_geometry import read_accessor
from PIL import Image
from pygltflib import GLTF2, BufferView
from render_generated import render

parser = argparse.ArgumentParser()
parser.add_argument("--job", type=Path, required=True)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
folder = args.job
output = args.output or folder / "refined"
output.mkdir(exist_ok=True)
landmarks = json.loads((folder / "face-landmarks-mp.json").read_text())
source = landmarks["concept"]
views = [v for v in ("front", "back") if landmarks[v].get("detected")]
if not source.get("detected") or len(views) != 1:
    (folder / "texture-refinement.json").write_text(
        json.dumps({"enabled": False, "reason": "no unambiguous face correspondence"})
    )
    raise SystemExit(0)
view = views[0]
target = landmarks[view]
sign = 1 if view == "front" else -1
projection = json.loads((folder / "projection.json").read_text())
center = np.array(projection["center"], np.float32)
extent = projection["extent"]
glb = GLTF2().load(str(folder / "model.glb"))
primitive = glb.meshes[0].primitives[0]
v = read_accessor(glb, primitive.attributes.POSITION)
f = read_accessor(glb, primitive.indices).reshape(-1, 3)
uv = read_accessor(glb, primitive.attributes.TEXCOORD_0)
tri = torch.tensor(f.astype(np.int32), device="cuda")
vertices = torch.tensor(v, device="cuda")[None]
ctx = dr.RasterizeCudaContext()
size = 2048
uv_clip = np.ones((len(uv), 4), np.float32)
uv_clip[:, :2] = uv * 2 - 1
uv_clip[:, 2] = 0
rast, _ = dr.rasterize(ctx, torch.tensor(uv_clip, device="cuda")[None], tri, (size, size))
world, _ = dr.interpolate(vertices, rast, tri)
qx = 0.5 + sign * (world[..., 0] - center[0]) / extent
qy = 0.5 - (world[..., 1] - center[1]) / extent
# Render frontmost depth, then reject texture pixels hidden behind other surfaces.
clip = np.ones((len(v), 4), np.float32)
clip[:, :3] = (v - center) / extent * 2
clip[:, 0] *= sign
clip[:, 2] *= -sign * 0.5
front_rast, _ = dr.rasterize(ctx, torch.tensor(clip, device="cuda")[None], tri, (1024, 1024))
front_world, _ = dr.interpolate(vertices, front_rast, tri)
lookup = torch.stack([qx, 1 - qy], dim=-1).contiguous()
front_z = dr.texture(
    front_world[..., 2:3].contiguous(), lookup, filter_mode="nearest", boundary_mode="clamp"
)[..., 0]
visible = (abs(front_z - world[..., 2]) < extent * 0.007) & (rast[..., 3] > 0)
# Three detected correspondences give a local affine map in normalized image coordinates.
keys = ("left_eye", "right_eye", "mouth")
affine = cv2.getAffineTransform(np.float32([target[k] for k in keys]), np.float32([source[k] for k in keys]))
sx = affine[0, 0] * qx + affine[0, 1] * qy + affine[0, 2]
sy = affine[1, 0] * qx + affine[1, 1] * qy + affine[1, 2]
reference = torch.tensor(
    np.asarray(Image.open(folder / "concept.png").convert("RGB"), dtype=np.float32) / 255, device="cuda"
).permute(2, 0, 1)[None]
color = F.grid_sample(
    reference,
    torch.stack([sx * 2 - 1, sy * 2 - 1], dim=-1),
    mode="bilinear",
    padding_mode="border",
    align_corners=False,
).permute(0, 2, 3, 1)
face_cx = (target["left_eye"][0] + target["right_eye"][0]) / 2
face_cy = (target["forehead"][1] + target["chin"][1]) / 2
rx = target["face_width"] * 0.55
ry = (target["chin"][1] - target["forehead"][1]) * 0.53
radius = torch.sqrt(((qx - face_cx) / rx) ** 2 + ((qy - face_cy) / ry) ** 2)
alpha = ((1.05 - radius) / 0.20).clamp(0, 1) * visible
coverage = int((alpha > 0.5).sum().item())
if coverage < 30:
    raise ValueError("Face projection does not cover sufficient visible texture area")
material = glb.materials[primitive.material]
image_index = glb.textures[material.pbrMetallicRoughness.baseColorTexture.index].source
bv = glb.bufferViews[glb.images[image_index].bufferView]
blob = glb.binary_blob()
raw = blob[bv.byteOffset : bv.byteOffset + bv.byteLength]
base = torch.tensor(
    np.asarray(Image.open(io.BytesIO(raw)).convert("RGB").resize((size, size)), dtype=np.float32) / 255,
    device="cuda",
)[None]
result = base * (1 - alpha[..., None]) + color * alpha[..., None]
atlas = Image.fromarray((result[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8))
buffer = io.BytesIO()
atlas.save(buffer, format="PNG")
png = buffer.getvalue()
merged = bytearray(blob)
merged.extend(b"\0" * ((-len(merged)) % 4))
index = len(glb.bufferViews)
glb.bufferViews.append(BufferView(buffer=0, byteOffset=len(merged), byteLength=len(png)))
merged.extend(png)
glb.images[image_index].bufferView = index
glb.buffers[0].byteLength = len(merged)
glb.set_binary_blob(bytes(merged))
glb.save_binary(str(output / "model.glb"))
report = {
    "enabled": True,
    "method": "visible-face UV projection from expanded concept with MediaPipe correspondences",
    "view": view,
    "texture_size": size,
    "covered_texels": coverage,
    "landmark_source": "MediaPipe FaceLandmarker float16 v1",
}
(folder / "texture-refinement.json").write_text(json.dumps(report, indent=2))
render(output)
print("FACE_TEXTURE_READY", coverage, flush=True)
