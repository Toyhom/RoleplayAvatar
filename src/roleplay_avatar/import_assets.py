"""Deterministic repairs for permissively licensed imported GLB assets."""

import hashlib
import json
import math
import struct
from pathlib import Path


def normalize_skin_weights(path: Path):
    raw = bytearray(path.read_bytes())
    source = hashlib.sha256(raw).hexdigest()
    if struct.unpack_from("<III", raw) != (0x46546C67, 2, len(raw)):
        raise ValueError("Invalid GLB header")
    length, kind = struct.unpack_from("<II", raw, 12)
    if kind != 0x4E4F534A:
        raise ValueError("Missing JSON chunk")
    doc = json.loads(raw[20 : 20 + length])
    binary_length, kind = struct.unpack_from("<II", raw, 20 + length)
    if kind != 0x004E4942 or 28 + length + binary_length > len(raw):
        raise ValueError("Missing BIN chunk")
    accessors = set()
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            weights = {
                key: value for key, value in primitive["attributes"].items() if key.startswith("WEIGHTS_")
            }
            if set(weights) - {"WEIGHTS_0"}:
                raise ValueError("Multiple weight sets require joint-set normalization")
            accessors.update(weights.values())
    repaired = 0
    max_error = 0
    for index in sorted(accessors):
        accessor = doc["accessors"][index]
        if accessor["type"] != "VEC4" or accessor["componentType"] != 5126 or "sparse" in accessor:
            raise ValueError("Weight repair supports dense float VEC4 only")
        view = doc["bufferViews"][accessor["bufferView"]]
        start = 28 + length + view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        stride = view.get("byteStride", 16)
        for vertex in range(accessor["count"]):
            offset = start + vertex * stride
            values = struct.unpack_from("<4f", raw, offset)
            total = sum(values)
            if not all(math.isfinite(v) and v >= 0 for v in values) or total <= 0:
                raise ValueError("Invalid skin weights")
            error = abs(total - 1)
            max_error = max(max_error, error)
            if error > 1e-6 or any(v > 1 for v in values):
                struct.pack_into("<4f", raw, offset, *(v / total for v in values))
                repaired += 1
    if repaired:
        path.write_bytes(raw)
    return {
        "method": "normalize_skin_weights",
        "vertices_repaired": repaired,
        "maximum_original_sum_error": max_error,
        "original_sha256": source,
        "result_sha256": hashlib.sha256(raw).hexdigest(),
    }
