"""Portable 2D-only packages keep voice/stream validation without requiring a GLB."""

import hashlib
import json
import shutil
import wave

import pytest
from conftest import ROOT
from PIL import Image
from pydantic import ValidationError

from roleplay_avatar.assets import load_package
from roleplay_avatar.contracts import CharacterPackage
from roleplay_avatar.creation import validate_creation_output


def test_3d_declaration_requires_geometry(characters):
    data = characters["humanoid_demo"].model_dump()
    data["profile"]["model"] = None
    with pytest.raises(ValidationError, match="3D"):
        CharacterPackage.model_validate(data)
    data["profile"]["presentation_modes"] = ["2d"]
    assert CharacterPackage.model_validate(data).profile.model is None


def test_portrait_package_is_portable_and_missing_atlas_is_rejected(tmp_path):
    folder = tmp_path / "character"
    shutil.copytree(ROOT / "fixtures/characters_m0/humanoid_demo", folder)
    profile = json.loads((folder / "profile.json").read_text())
    profile.update(model=None, presentation_modes=["2d"], package_status="validated")
    (folder / "profile.json").write_text(json.dumps(profile))
    (folder / "puppet").mkdir()
    Image.new("RGBA", (128, 128), (140, 100, 80, 255)).save(folder / "puppet/portrait.png")
    (folder / "puppet/rig.json").write_text(
        json.dumps(
            {
                "renderer": "deformable-portrait",
                "image": "portrait.png",
                "mouth_binding": {
                    "atlas": "mouth-atlas.png",
                    "roi_px": [40, 70, 40, 25],
                    "source_sha256": hashlib.sha256(
                        (folder / "puppet/portrait.png").read_bytes()
                    ).hexdigest(),
                    "tile_size": 192,
                    "jaw_steps": 8,
                    "round_steps": 3,
                    "smile_steps": 2,
                },
            }
        )
    )
    with wave.open(str(folder / "voice.wav"), "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 3200)
    (folder / "voice.txt").write_text("Fixture only")
    voice = json.loads((folder / "voice_profile.json").read_text())
    voice.update(
        reference_audio="voice.wav",
        reference_text="voice.txt",
        reference_sha256=hashlib.sha256((folder / "voice.wav").read_bytes()).hexdigest(),
    )
    (folder / "voice_profile.json").write_text(json.dumps(voice))
    (folder / "qa_report.json").write_text(
        json.dumps({"status": "passed", "checks": {"portrait": "passed"}, "known_issues": []})
    )
    with pytest.raises(ValueError, match="missing mouth atlas"):
        load_package(folder, require_assets=True)
    Image.new("RGBA", (1536, 1152)).save(folder / "puppet/mouth-atlas.png")
    (folder / "puppet/mouth-generation.json").write_text("{}")
    assert load_package(folder, require_assets=True).profile.model is None
    (folder / "generation.json").write_text("{}")
    with pytest.raises(ValueError, match="automatic source-lip"):
        validate_creation_output(folder)
    rig = json.loads((folder / "puppet/rig.json").read_text())
    original_roi = rig["mouth_binding"]["roi_px"]
    rig["mouth_binding"]["roi_px"] = [120, 120, 40, 40]
    (folder / "puppet/rig.json").write_text(json.dumps(rig))
    with pytest.raises(ValueError, match="outside the portrait"):
        load_package(folder, require_assets=True)
    rig["mouth_binding"]["roi_px"] = original_roi
    (folder / "puppet/rig.json").write_text(json.dumps(rig))
    rig["mouth_binding"].update(
        method="source-lip-warp-v3",
        jaw_steps=0,
        round_steps=0,
        smile_steps=0,
        lip_x_px=[45, 75],
        lip_curve_y_px=[80] * 33,
        max_open_px=10,
    )
    Image.new("RGBA", (384, 192)).save(folder / "puppet/mouth-atlas.png")
    (folder / "puppet/rig.json").write_text(json.dumps(rig))
    assert load_package(folder, require_assets=True).profile.model is None
    validate_creation_output(folder)
    generation = json.loads((folder / "generation.json").read_text())
    assert generation["automatic_features"]["manual_asset_edits"] is False
    assert len(generation["automatic_features"]["actions"]) == 8
    rig["mouth_binding"]["lip_curve_y_px"][16] = float("nan")
    (folder / "puppet/rig.json").write_text(json.dumps(rig))
    with pytest.raises(ValueError, match="source lip geometry"):
        load_package(folder, require_assets=True)
    rig["mouth_binding"]["lip_curve_y_px"][16] = 80
    (folder / "puppet/rig.json").write_text(json.dumps(rig))
    (folder / "voice.wav").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_package(folder, require_assets=True)
