"""Validate atlas/source association and save actual replacement composites for review."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from roleplay_avatar.assets import load_package

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("--characters", nargs="+", required=True)
p.add_argument("--root", type=Path, default=ROOT / "characters")
p.add_argument("--output", type=Path, required=True)
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
poses = [("closed", 0, 0), ("mid", 0, 3), ("open", 0, 7), ("round", 2, 7), ("smile", 3, 7)]
sheet = Image.new("RGB", (256 * len(poses), 290 * len(args.characters)), "#f1f5ed")
report = []
for row, cid in enumerate(args.characters):
    folder = args.root / cid
    load_package(folder, require_assets=True)
    rig = json.loads((folder / "puppet/rig.json").read_text())
    binding = rig["mouth_binding"]
    if binding.get("method") == "source-lip-warp-v3":
        raise SystemExit("Continuous v3 mouths require scripts/check_2d_performance.py for actual rendered QA")
    art = Image.open(folder / "puppet/portrait.png").convert("RGBA")
    atlas = Image.open(folder / "puppet/mouth-atlas.png").convert("RGBA")
    x, y, width, height = binding["roi_px"]
    tile = binding["tile_size"]
    lm = rig["landmarks"]
    face = lm["face_width"] * art.width
    cx = lm["mouth"][0] * art.width
    ey = (lm["left_eye"][1] + lm["right_eye"][1]) * art.height / 2
    crop = (cx - face * 0.7, ey - face * 0.4, cx + face * 0.7, ey + face)
    frames = []
    for label, atlas_row, col in poses:
        rendered = art.copy()
        patch = atlas.crop((col * tile, atlas_row * tile, (col + 1) * tile, (atlas_row + 1) * tile))
        rendered.alpha_composite(patch.resize((round(width), round(height))), (round(x), round(y)))
        rendered = rendered.crop(crop).resize((256, 256), Image.Resampling.LANCZOS)
        frames.append(rendered)
        column = len(frames) - 1
        sheet.paste(rendered, (column * 256, row * 290 + 25), rendered)
        ImageDraw.Draw(sheet).text(
            (column * 256 + 8, row * 290 + 8), cid[-6:] + " / " + label, fill="#243e36"
        )
    report.append({"character": cid, "mouth_binding": binding, "source_and_layout_validated": True})
sheet.save(args.output / "mouth-composites.png")
(args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
print("MOUTH_ASSETS_PASS", len(report))
