"""Exercise the actual CUDA extension paths before accepting an asset worker."""

import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "third_party/anigen"))
sys.modules["cupy"] = None
os.environ["ATTN_BACKEND"] = "sdpa"
os.environ["SPARSE_ATTN_BACKEND"] = "flash_attn"
import nvdiffrast.torch as dr
import spconv.pytorch as spconv
import torch
from pytorch3d.ops import knn_points

points = torch.randn(1, 32, 3, device="cuda")
result = knn_points(points, points, K=1)
assert result.dists.max().item() < 1e-5
ctx = dr.RasterizeCudaContext()
vertices = torch.tensor(
    [[[-0.5, -0.5, 0, 1], [0.5, -0.5, 0, 1], [0, 0.5, 0, 1]]], device="cuda", dtype=torch.float32
)
indices = torch.tensor([[0, 1, 2]], device="cuda", dtype=torch.int32)
rast, _ = dr.rasterize(ctx, vertices, indices, resolution=(32, 32))
assert rast[..., 3].sum() > 0
sparse = spconv.SparseConvTensor(
    torch.randn(4, 4, device="cuda"),
    torch.tensor([[0, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]], device="cuda", dtype=torch.int32),
    [3, 3, 3],
    1,
)
conv = spconv.SubMConv3d(4, 8, 3, padding=1).cuda()
assert conv(sparse).features.shape == (4, 8)
from anigen.pipelines import AnigenImageTo3DPipeline

assert callable(AnigenImageTo3DPipeline.from_pretrained)
print("ASSET_WITNESS_OK", torch.cuda.get_device_name(), flush=True)
