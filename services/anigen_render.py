"""Color-only multiview teacher for AniGen texture baking.

The texture baker only consumes RGB. Avoid the upstream per-face normal and
antialias passes on dense generated topology; use 2x supersampling instead.
All shape, skeleton, skin and color values remain model-generated.
"""

import json
from pathlib import Path

import numpy as np
import nvdiffrast.torch as dr
import torch
import torch.nn.functional as F


def install(folder):
    from anigen.utils import render_utils
    from anigen.utils.random_utils import sphere_hammersley_sequence

    folder = Path(folder)

    def multiview(sample, resolution=512, nviews=30):
        vertices = sample.vertices.detach().float().contiguous()
        faces = sample.faces.detach().int().contiguous()
        colors = sample.vertex_attrs[:, :3].detach().float().contiguous()
        if not torch.isfinite(vertices).all() or not torch.isfinite(colors).all():
            raise ValueError("Non-finite generated surface")
        if faces.min() < 0 or faces.max() >= vertices.shape[0]:
            raise ValueError("Invalid generated surface indices")
        np.savez_compressed(
            folder / "dense-surface.npz",
            vertices=vertices.cpu().numpy(),
            faces=faces.cpu().numpy(),
            colors=colors.cpu().numpy(),
        )
        cams = [sphere_hammersley_sequence(i, nviews) for i in range(nviews)]
        extrinsics, intrinsics = render_utils.yaw_pitch_r_fov_to_extrinsics_intrinsics(
            [p[0] for p in cams], [p[1] for p in cams], 2, 40
        )
        from anigen.renderers.mesh_renderer import intrinsics_to_projection

        context = dr.RasterizeCudaContext()
        homogeneous = torch.cat([vertices, torch.ones_like(vertices[:, :1])], dim=1)[None]
        images = []
        for index, (extr, intr) in enumerate(zip(extrinsics, intrinsics)):
            projection = intrinsics_to_projection(intr, 1, 100)
            clip = homogeneous @ (projection @ extr).T
            if not torch.isfinite(clip).all():
                raise ValueError("Non-finite projection")
            rast, _ = dr.rasterize(context, clip, faces, (resolution * 2, resolution * 2))
            color, _ = dr.interpolate(colors[None], rast, faces)
            color = F.interpolate(
                color.permute(0, 3, 1, 2),
                (resolution, resolution),
                mode="bilinear",
                align_corners=False,
                antialias=True,
            )
            images.append((color[0].permute(1, 2, 0).clamp(0, 1).cpu().numpy() * 255).astype(np.uint8))
            if (index + 1) % 20 == 0:
                print("TEXTURE_VIEWS", index + 1, nviews, flush=True)
        (folder / "texture-rendering.json").write_text(
            json.dumps(
                {
                    "method": "nvdiffrast color interpolation with 2x supersampling",
                    "views": nviews,
                    "resolution": resolution,
                    "dense_vertices": vertices.shape[0],
                    "dense_triangles": faces.shape[0],
                },
                indent=2,
            )
        )
        return images, [e.cpu() for e in extrinsics], [i.cpu() for i in intrinsics]

    render_utils.render_multiview = multiview
