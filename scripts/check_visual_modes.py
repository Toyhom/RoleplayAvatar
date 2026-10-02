"""Capture actual mouth/expression pixels in both renderers, including a stylized face."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/browsers"))
p = argparse.ArgumentParser()
p.add_argument("--characters", nargs="+", required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--modes", nargs="+", choices=["2d", "3d"], default=["2d"])
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=True)


async def main():
    errors = []
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto("http://127.0.0.1:18080/?lang=zh-CN")
        await page.wait_for_function("window.avatarPresentation?.loaded")
        for cid in args.characters:
            await page.evaluate("id=>window.avatarStudio.refresh(id)", cid)
            for mode in args.modes:
                await page.evaluate("mode=>window.avatarPresentation.switch(mode)", mode)
                await page.wait_for_function("window.avatarPresentation.loaded")
                await page.evaluate(
                    "()=>{window.avatarPresentation.closeup=true;window.avatarPresentation.frameView();}"
                )
                for emotion in ["auto", "mouth", "happy", "sad", "angry"]:
                    await page.locator(f'[data-expression="{emotion}"]').click()
                    await page.wait_for_timeout(800)
                    await page.screenshot(path=str(args.output / f"{cid}-{mode}-{emotion}.png"))
                results.append(
                    await page.evaluate(
                        "()=>({scene:window.avatarSceneInfo,motion:window.avatarMotionEvidence})"
                    )
                )
                await page.locator('[data-expression="auto"]').click()
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.evaluate("()=>window.avatarPresentation.switch('2d')")
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
        assert await page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        await browser.close()
    assert not errors, errors
    (args.output / "report.json").write_text(
        json.dumps(
            {"scenes": results, "page_errors": errors, "mobile_overflow": False}, ensure_ascii=False, indent=2
        )
    )
    print("VISUAL_CAPTURE_PASS", flush=True)


asyncio.run(main())
