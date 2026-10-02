import json
import struct

import pytest

from roleplay_avatar.import_assets import normalize_skin_weights


def test_weight_repair_preserves_vertices_and_reports_source(tmp_path):
    doc = {
        "meshes": [{"primitives": [{"attributes": {"WEIGHTS_0": 0}}]}],
        "accessors": [{"bufferView": 0, "type": "VEC4", "componentType": 5126, "count": 2}],
        "bufferViews": [{"byteOffset": 0, "byteLength": 32}],
    }
    text = json.dumps(doc).encode()
    text += b" " * ((-len(text)) % 4)
    binary = struct.pack("<8f", 0.8, 0.6, 0.2, 0, 1.000000119, 0, 0, 0)
    raw = struct.pack("<III", 0x46546C67, 2, 28 + len(text) + len(binary))
    raw += (
        struct.pack("<II", len(text), 0x4E4F534A)
        + text
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )
    path = tmp_path / "test.glb"
    path.write_bytes(raw)
    report = normalize_skin_weights(path)
    assert report["vertices_repaired"] == 2
    assert report["original_sha256"] != report["result_sha256"]
    result = path.read_bytes()
    assert result[: 28 + len(text)] == raw[: 28 + len(text)]
    assert struct.unpack_from("<4f", result, 28 + len(text)) == pytest.approx((0.5, 0.375, 0.125, 0))
    assert normalize_skin_weights(path)["vertices_repaired"] == 0
