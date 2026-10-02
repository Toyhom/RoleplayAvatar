"""Select an existing head joint using measured face bounds and actual skin influence."""

import numpy as np
from glb_geometry import read_accessor


def select_head(glb, analysis, projection):
    if not analysis.get("landmark_validated") or not analysis.get("chin"):
        return None
    primitive = glb.meshes[0].primitives[0]
    vertices = read_accessor(glb, primitive.attributes.POSITION)
    weights = read_accessor(glb, primitive.attributes.WEIGHTS_0)
    joints = read_accessor(glb, primitive.attributes.JOINTS_0)
    extent = projection["extent"]
    center = projection["center"]
    width = analysis["face_width"] * extent
    sign = 1 if analysis["view"] == "front" else -1
    x = center[0] + sign * (analysis["chin"][0] - 0.5) * extent
    y = center[1] + (0.5 - analysis["chin"][1]) * extent
    # A fixed top-22% slice misses the lower half of large cartoon heads.
    region = (vertices[:, 1] > y - width * 0.08) & (abs(vertices[:, 0] - x) < width * 0.72)
    if region.sum() < 30:
        return None
    candidates = []
    for ordinal, index in enumerate(glb.skins[0].joints):
        if index == glb.skins[0].skeleton:
            continue
        influence = np.sum(weights * (joints == ordinal), axis=1)
        mass = float(influence[region].sum())
        purity = mass / max(float(influence.sum()), 1e-6)
        coverage = mass / int(region.sum())
        if purity >= 0.65 and mass > 50 and coverage > 0.25:
            candidates.append(
                {
                    "node": index,
                    "joint": glb.nodes[index].name,
                    "purity": purity,
                    "coverage": coverage,
                    "weighted_vertices": mass,
                    "method": "measured chin and face width plus skin influence",
                }
            )
    return max(candidates, key=lambda entry: entry["weighted_vertices"] * entry["purity"], default=None)
