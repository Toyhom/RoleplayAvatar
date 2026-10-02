"""Conservative, image-landmark-guided local expression morphs for generated faces.

This is geometric expression fitting, not a learned phoneme/FLAME reconstruction.
Uncertain or absent landmarks disable fitting instead of inventing face channels.
"""

import numpy as np
from glb_geometry import add_array, add_vec3, read_accessor
from pygltflib import Attributes, Material, PbrMetallicRoughness, Primitive


def fit(glb, analysis, projection):
    detected = (
        analysis.get("landmark_method") == "mediapipe-face-landmarker"
        and analysis.get("landmark_validated") is True
    )
    if not analysis.get("face_visible") or (not detected and analysis.get("confidence", 0) < 0.8):
        return {"enabled": False, "reason": "no confident visible humanoid face"}
    fw = analysis.get("face_width", 0)
    if not isinstance(fw, (int, float)) or not 0.025 < fw < 0.75:
        return {"enabled": False, "reason": "face scale outside supported range"}
    sign = 1 if analysis["view"] == "front" else -1
    center = np.asarray(projection["center"])
    extent = projection["extent"]
    width = fw * extent
    points = {}
    for name in ("mouth", "left_eye", "right_eye"):
        point = np.asarray(analysis.get(name, []), dtype=float)
        if point.shape != (2,) or not np.isfinite(point).all() or np.any((point <= 0) | (point >= 1)):
            return {"enabled": False, "reason": "invalid face landmarks"}
        points[name] = np.array(
            [center[0] + sign * (point[0] - 0.5) * extent, center[1] + (0.5 - point[1]) * extent]
        )
    eyes = (points["left_eye"] + points["right_eye"]) / 2
    distance = np.linalg.norm(points["left_eye"] - points["right_eye"])
    if (
        not 0.18 * width < distance < 0.9 * width
        or not 0 < eyes[1] - points["mouth"][1] < width
        or abs(points["left_eye"][1] - points["right_eye"][1]) > width * 0.3
    ):
        return {"enabled": False, "reason": "inconsistent facial landmarks"}
    primitive = glb.meshes[0].primitives[0]
    v = read_accessor(glb, primitive.attributes.POSITION)
    head = (abs(v[:, 0] - eyes[0]) < width * 0.55) & (abs(v[:, 1] - eyes[1]) < width * 0.7)
    if head.sum() < 30:
        return {"enabled": False, "reason": "insufficient face geometry"}
    front = np.quantile(sign * v[head, 2], 0.8)
    depth = np.exp(-(((sign * v[:, 2] - front) / (width * 0.38)) ** 2))

    def zone(point, rx, ry):
        return (
            np.exp(-(((v[:, 0] - point[0]) / (width * rx)) ** 2) - ((v[:, 1] - point[1]) / (width * ry)) ** 2)
            * depth
        )

    mouth = points["mouth"]
    mouth_width = width * 0.3
    if analysis.get("mouth_corners"):
        mouth_width = float(np.linalg.norm(np.diff(np.asarray(analysis["mouth_corners"]), axis=0))) * extent
    mouth_width = np.clip(mouth_width, width * 0.16, width * 0.5)
    mouth_area = zone(mouth, 0.28, 0.24)
    jaw = np.zeros_like(v)
    jaw[:, 1] = -width * 0.12 * mouth_area * np.clip((mouth[1] - v[:, 1]) / width * 7 + 0.5, 0, 1)
    jaw[:, 2] = sign * width * 0.025 * mouth_area
    blink = np.zeros_like(v)
    happy = np.zeros_like(v)
    sad = np.zeros_like(v)
    angry = np.zeros_like(v)
    for eye in (points["left_eye"], points["right_eye"]):
        mask = zone(eye, 0.19, 0.1)
        blink[:, 1] += (eye[1] - v[:, 1]) * mask * 0.92
        brow = eye + np.array([0, width * 0.1])
        brow_mask = zone(brow, 0.22, 0.11)
        inward = np.clip(1 - abs(v[:, 0] - eyes[0]) / width * 2, 0, 1)
        sad[:, 1] += width * 0.045 * brow_mask * inward
        angry[:, 1] -= width * 0.045 * brow_mask * inward
    corners = mouth_area * np.clip(abs(v[:, 0] - mouth[0]) / width * 5, 0, 1)
    happy[:, 1] = width * 0.085 * corners
    sad[:, 1] -= width * 0.06 * corners
    soft = happy * 0.3
    channels = {"jaw_open": jaw, "blink": blink, "happy": happy, "sad": sad, "angry": angry, "soft": soft}
    rounded = np.zeros_like(v)
    rounded[:, 0] = -(v[:, 0] - mouth[0]) * mouth_area * 0.4
    rounded[:, 2] = sign * width * 0.025 * mouth_area
    wide = np.zeros_like(v)
    wide[:, 0] = (v[:, 0] - mouth[0]) * mouth_area * 0.3
    channels.update(mouth_round=rounded, mouth_wide=wide, brow_up=-angry * 1.5, eye_squint=blink * 0.4)
    for name, delta in channels.items():
        if not np.isfinite(delta).all() or np.linalg.norm(delta, axis=1).max() > width * 0.17:
            return {"enabled": False, "reason": "unsafe morph displacement"}
    if np.count_nonzero(np.linalg.norm(jaw, axis=1) > width * 0.005) < 10:
        return {"enabled": False, "reason": "mouth area has insufficient geometry"}
    primitive.targets = [Attributes(POSITION=add_vec3(glb, delta)) for delta in channels.values()]
    glb.meshes[0].extras = {**(glb.meshes[0].extras or {}), "targetNames": list(channels)}
    glb.meshes[0].weights = [0.0] * len(channels)
    # A sealed reconstructed surface cannot expose a mouth interior by stretching.
    # Add a skinned oral insert: closed at rest, visibly open with the jaw channel.
    # This is an explicit repair layer, not a claim of recovered anatomical topology.
    face_ids = np.where(head & (sign * v[:, 2] > front - width * 0.3))[0]
    nearest = face_ids[np.argsort(np.linalg.norm(v[face_ids, :2] - mouth, axis=1))[:12]]
    # Include the whole opening's swept footprint: the reconstructed lower lip
    # can protrude farther than the centre landmark, occluding a flat insert.
    footprint = head & (abs(v[:, 0] - mouth[0]) < mouth_width * 0.65)
    footprint &= (v[:, 1] > mouth[1] - width * 0.22) & (v[:, 1] < mouth[1] + width * 0.055)
    surface_z = np.max(sign * v[footprint, 2]) if footprint.any() else np.max(sign * v[nearest, 2])
    mouth_z = sign * (surface_z + width * 0.04)
    weights = read_accessor(glb, primitive.attributes.WEIGHTS_0)[nearest[0]]
    joints = read_accessor(glb, primitive.attributes.JOINTS_0)[nearest[0]]

    def insert(name, color, x, y, z_shift=0):
        position = np.column_stack(
            (mouth[0] + x, np.full(len(x), mouth[1]), np.full(len(x), mouth_z + sign * z_shift))
        ).astype(np.float32)
        tri = np.array([[0, i, i + 1] for i in range(1, len(x) - 1)], dtype=np.uint32)
        glb.materials.append(
            Material(
                name=name,
                doubleSided=True,
                pbrMetallicRoughness=PbrMetallicRoughness(
                    baseColorFactor=[*color, 1], metallicFactor=0, roughnessFactor=0.8
                ),
            )
        )
        attributes = Attributes(
            POSITION=add_vec3(glb, position),
            NORMAL=add_vec3(glb, np.tile([0, 0, sign], (len(x), 1))),
            WEIGHTS_0=add_array(glb, np.tile(weights, (len(x), 1)), "VEC4"),
            JOINTS_0=add_array(glb, np.tile(joints, (len(x), 1)), "VEC4", component=5123),
        )
        targets = []
        for channel in channels:
            delta = np.zeros_like(position)
            if channel == "jaw_open":
                delta[:, 1] = y
            elif channel == "mouth_round":
                delta[:, 0] = -x * 0.4
            elif channel == "mouth_wide":
                delta[:, 0] = x * 0.3
            targets.append(Attributes(POSITION=add_vec3(glb, delta)))
        glb.meshes[0].primitives.append(
            Primitive(
                attributes=attributes,
                indices=add_array(glb, tri.reshape(-1), "SCALAR", component=5125, target=34963),
                material=len(glb.materials) - 1,
                mode=4,
                targets=targets,
            )
        )

    theta = np.linspace(0, np.pi * 2, 65)
    x = np.r_[0, np.cos(theta) * mouth_width * 0.49]
    y = np.r_[-width * 0.055, -width * 0.055 + np.sin(theta) * width * 0.09]
    insert("MouthInterior", [0.095, 0.016, 0.025], x, y)
    insert("Tongue", [0.53, 0.11, 0.16], x * 0.66, y * 0.26 - width * 0.095, width * 0.001)
    # A short upper dental strip stays inside the oral opening at every jaw weight.
    teeth_x = np.array([-0.36, 0.36, 0.32, -0.32, -0.36]) * mouth_width
    teeth_y = np.array([0.014, 0.014, -0.015, -0.015, 0.014]) * width
    insert("UpperTeeth", [0.96, 0.91, 0.8], teeth_x, teeth_y, width * 0.002)
    return {
        "enabled": True,
        "channels": list(channels),
        "face_width": float(width),
        "method": ("MediaPipe" if detected else "VLM") + "-guided local morphs with skinned oral insert",
        "oral_insert": {
            "mouth_width": float(mouth_width),
            "center": [*mouth.tolist(), float(mouth_z)],
            "max_gap": float(width * 0.18),
            "parts": ["MouthInterior", "Tongue", "UpperTeeth"],
        },
        "max_displacements": {k: float(np.linalg.norm(d, axis=1).max()) for k, d in channels.items()},
    }
