"""Render mouth continuity and finite action clips in the real browser, no GPU models."""

import argparse
import asyncio
import io
import json
import os
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/browsers"))
p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, required=True)
p.add_argument("--asset-root", type=Path)
p.add_argument("--characters", nargs="+", required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)


async def main():
    report = {"characters": [], "actions": [], "errors": []}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: report["errors"].append(str(e)))
        if a.asset_root:

            async def asset(route):
                rel = route.request.url.split("/assets/")[1]
                path = a.asset_root / rel
                if path.is_file():
                    await route.fulfill(path=str(path))
                else:
                    await route.continue_()

            await page.route("**/assets/**/puppet/*", asset)
        await page.goto("http://127.0.0.1:18080/?lang=zh-CN")
        await page.wait_for_function("window.avatarPresentation?.loaded")

        async def draw(values, action=None, seconds=0):
            await page.evaluate(
                """([values,action,seconds])=>{
                const s=window.avatarPresentation,v=s.current;
                s.preview=null;v.actionPreview=null;v.look=[0,0];v.smooth={...values};
                performance.now=()=>10000;v.last=9900;
                s.setPerformance(action?{actions:[{name:action,start_s:0,duration_s:2,strength:.85}],action_time_s:seconds}:null,{values});
                v.render();
            }""",
                [values, action, seconds],
            )
            # Read the WebGL framebuffer itself, excluding overlay labels.
            data = await page.evaluate("window.avatarPresentation.current.canvas.toDataURL()")
            import base64

            return Image.open(io.BytesIO(base64.b64decode(data.split(",")[1]))).convert("RGB")

        sheet = Image.new("RGB", (240 * 6, 240 * len(a.characters)), "#f1f5ed")
        for row, cid in enumerate(a.characters):
            await page.evaluate("id=>window.avatarStudio.refresh(id)", cid)
            await page.wait_for_function("window.avatarPresentation.loaded")
            await page.evaluate("()=>{let s=window.avatarPresentation;s.closeup=true;s.frameView();}")
            poses = [
                ("closed", 0, 0, 0),
                ("slight", 0.06, 0, 0),
                ("mid", 0.45, 0, 0),
                ("open", 1, 0, 0),
                ("round", 0.7, 1, 0),
                ("smile", 0.6, 0, 1),
            ]
            pictures = []
            for col, (label, jaw, rounding, happy) in enumerate(poses):
                im = await draw({"jaw_open": jaw, "mouth_round": rounding, "happy": happy})
                im.save(a.output / f"{cid}-{label}.png")
                pictures.append(im)
                # Crop around the rendered face using the known projection.
                rig = await page.evaluate("window.avatarPresentation.current.rig")
                w, h = im.size
                fw = rig["landmarks"]["face_width"]
                iw, ih = rig["width"], rig["height"]
                scale = min(w / (iw * 1.1), h / (ih * 1.08)) * min(2.2, max(1.1, 0.5 / fw))
                face = fw * iw * scale
                ey = h / 2 - fw * iw * 0.35 * scale
                crop = (w / 2 - face * 0.72, ey - face * 0.30, w / 2 + face * 0.72, ey + face * 1.02)
                thumb = im.crop(crop).resize((240, 220))
                sheet.paste(thumb, (col * 240, row * 240 + 20))
                ImageDraw.Draw(sheet).text(
                    (col * 240 + 5, row * 240 + 3), cid[-6:] + " / " + label, fill="#253d32"
                )
            binding = rig["mouth_binding"]
            assert binding["method"] == "source-lip-warp-v3"
            neutral_error = None
            if not binding["missing_source_mouth_repaired"]:
                await page.evaluate(
                    "()=>{let v=window.avatarPresentation.current;v._binding=v.rig.mouth_binding;delete v.rig.mouth_binding;}"
                )
                raw = await draw({})
                diff = ImageChops.difference(raw, pictures[0])
                neutral_error = max(v[1] for v in diff.getextrema())
                assert neutral_error <= 2, neutral_error
                await page.evaluate(
                    "()=>{let v=window.avatarPresentation.current;v.rig.mouth_binding=v._binding;}"
                )
            assert ImageChops.difference(pictures[0], pictures[3]).getbbox()
            report["characters"].append(
                {"id": cid, "neutral_max_channel_error": neutral_error, "binding": binding["method"]}
            )
        sheet.save(a.output / "mouth-comparison.png")
        names = ["nod", "shake_head", "tilt", "bow", "lean_forward", "lean_back", "sway", "bounce"]
        rest = await draw({})
        action_sheet = Image.new("RGB", (320 * 4, 260 * 2), "#f1f5ed")
        for i, name in enumerate(names):
            im = await draw({}, name, 0.72)
            im.save(a.output / f"action-{name}.png")
            diff = ImageChops.difference(rest, im)
            changed = sum(
                count for count, value in diff.convert("L").getcolors(im.width * im.height) if value > 8
            )
            assert changed > 200, (name, changed)
            end = await draw({}, name, 2.01)
            assert ImageChops.difference(rest, end).getbbox() is None, name
            report["actions"].append({"name": name, "changed_pixels": changed, "returns_to_rest": True})
            action_sheet.paste(im.resize((320, 240)), ((i % 4) * 320, (i // 4) * 260 + 20))
            ImageDraw.Draw(action_sheet).text(((i % 4) * 320 + 5, (i // 4) * 260 + 3), name, fill="#253d32")
        action_sheet.save(a.output / "action-comparison.png")
        await page.evaluate("()=>window.avatarPresentation.setMode('listening')")
        assert not await page.evaluate("window.avatarPresentation.current.frame")
        assert not report["errors"], report["errors"]
        await browser.close()
    (a.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("2D_PERFORMANCE_PASS", json.dumps(report), flush=True)


asyncio.run(main())
