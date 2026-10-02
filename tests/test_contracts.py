import json
import math
import shutil

import pytest
from conftest import ROOT
from pydantic import ValidationError

from roleplay_avatar.adapters import AudioChunk, CreatureAdapter, supported_style
from roleplay_avatar.assets import inside, load_package
from roleplay_avatar.contracts import CharacterPackage, Segment, SpeakRequest


@pytest.mark.parametrize("name", ["humanoid_demo", "dragon_demo", "robot_demo"])
def test_templates_are_contract_valid_but_not_real_assets(name):
    package = load_package(ROOT / "fixtures/characters_m0" / name)
    assert package.profile.package_status == "template_only"
    with pytest.raises(ValueError, match="missing asset"):
        load_package(ROOT / "fixtures/characters_m0" / name, require_assets=True)


@pytest.mark.parametrize(
    "case", ["cycle", "missing_parent", "unbounded", "face_wait", "no_jaw", "fallback_cycle"]
)
def test_invalid_package_rejected(characters, case):
    data = characters["dragon_demo"].model_dump()
    if case == "cycle":
        data["rig_map"]["joints"][1]["parent"] = "Jaw"
    elif case == "missing_parent":
        data["rig_map"]["joints"][1]["parent"] = "Missing"
    elif case == "unbounded":
        data["rig_map"]["joints"][2]["angle_limits_deg"] = [-900, 900]
    elif case == "face_wait":
        data["capabilities"]["active_streams"].append("face")
    elif case == "no_jaw":
        data["rig_map"]["joints"][2]["semantic"] = "tail"
    elif case == "fallback_cycle":
        data["motion_manifest"]["motions"]["idle"] = {"fallback": "listen"}
    with pytest.raises(ValidationError):
        CharacterPackage.model_validate(data)


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd"])
def test_asset_path_cannot_escape(tmp_path, path):
    with pytest.raises(ValueError, match="escapes"):
        inside(tmp_path, path)


def test_symlink_cannot_escape(tmp_path):
    (tmp_path / "outside").symlink_to("/etc")
    with pytest.raises(ValueError):
        inside(tmp_path, "outside/passwd")


def test_controller_respects_actual_capabilities_and_normalizes_rotations(characters):
    segment = Segment(turn_id="test", segment_id=0, sequence=0, text="test", intensity=1)
    chunk = AudioChunk(b"\xff\x7f" * 2400, 12000)
    adapter = CreatureAdapter()
    robot = adapter.frame(characters["robot_demo"], segment, chunk)
    assert set(robot["rotations_delta_xyzw"]) == {"Sensor"}
    assert robot["face_driver"] == "none"
    dragon = adapter.frame(characters["dragon_demo"], segment, chunk)
    for q in dragon["rotations_delta_xyzw"].values():
        assert sum(v * v for v in q) == pytest.approx(1)
    assert math.degrees(2 * math.acos(dragon["rotations_delta_xyzw"]["Jaw"][3])) <= 20


def test_unsupported_style_falls_back_and_base_rejects_claimed_styles(characters):
    assert supported_style("angry", characters["dragon_demo"]) == "neutral"
    data = characters["dragon_demo"].model_dump()
    data["voice_profile"].update(backend="qwen3_base", supported_styles=["neutral", "happy"])
    with pytest.raises(ValidationError):
        CharacterPackage.model_validate(data)


def test_llm_cannot_supply_arbitrary_execution_fields():
    with pytest.raises(ValidationError):
        SpeakRequest(type="speak", turn_id="test", character_id="dragon_demo", text="x", command="bad")


def test_generated_provenance_roundtrip_and_path_boundary(tmp_path):
    shutil.copytree(ROOT / "fixtures/characters_m0/humanoid_demo", tmp_path / "character")
    folder = tmp_path / "character"
    provenance = {
        "kind": "generated_asset",
        "seed": 42,
        "sources": [{"component": "geometry_skeleton_skin", "seed": "42", "renderer": "color"}],
        "generation_record": "generation.json",
        "notes": "Generation parameters retained.",
    }
    (folder / "provenance.json").write_text(json.dumps(provenance))
    assert load_package(folder).provenance.generation_record == "generation.json"
    provenance["generation_record"] = "../outside.json"
    (folder / "provenance.json").write_text(json.dumps(provenance))
    with pytest.raises(ValueError, match="escapes"):
        load_package(folder)


def test_2d_package_paths_cannot_escape(tmp_path):
    folder = tmp_path / "character"
    shutil.copytree(ROOT / "fixtures/characters_m0/humanoid_demo", folder)
    profile = json.loads((folder / "profile.json").read_text())
    assert load_package(folder).profile.presentation_modes == ["3d"]
    profile["presentation_modes"] = ["2d"]
    (folder / "profile.json").write_text(json.dumps(profile))
    (folder / "puppet").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        load_package(folder)
    profile["presentation_modes"] = []
    (folder / "profile.json").write_text(json.dumps(profile))
    with pytest.raises(ValidationError):
        load_package(folder)
