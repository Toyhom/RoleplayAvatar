import json

import pytest

from roleplay_avatar.assets import cubism_files


def test_declared_native_files_and_path_boundary(tmp_path):
    folder = tmp_path / "live2d"
    folder.mkdir()
    manifest = folder / "example.model3.json"
    data = {
        "Version": 3,
        "FileReferences": {
            "Moc": "example.moc3",
            "Textures": ["textures/one.png"],
            "Motions": {"Idle": [{"File": "motions/idle.motion3.json", "FadeInTime": 0.5}]},
            "Expressions": [{"Name": "Smile", "File": "expressions/smile.exp3.json"}],
        },
    }
    manifest.write_text(json.dumps(data))
    assert cubism_files(tmp_path, "live2d/example.model3.json") == {
        "live2d/example.model3.json",
        "live2d/example.moc3",
        "live2d/textures/one.png",
        "live2d/motions/idle.motion3.json",
        "live2d/expressions/smile.exp3.json",
    }
    data["FileReferences"]["Moc"] = "../private.json"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        cubism_files(tmp_path, "live2d/example.model3.json")
    data["FileReferences"]["Moc"] = "/etc/passwd"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        cubism_files(tmp_path, "live2d/example.model3.json")
