"""Render imported native models, inspect authored mouth/physics/clips, and speak."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/browsers"))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--characters", nargs="+", default=["sample_haru", "sample_hiyori", "sample_robot"])
parser.add_argument("--output", type=Path, default=ROOT / "outputs/product-sessions/native-library")
args = parser.parse_args()
OUT = args.output
OUT.mkdir(parents=True, exist_ok=True)


async def main():
    errors = []
    report = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "console",
            lambda msg: (
                print("BROWSER", msg.type, msg.text[:350], flush=True) if msg.type == "error" else None
            ),
        )
        await page.goto("http://127.0.0.1:18080/?lang=zh-CN")
        await page.wait_for_function("window.avatarPresentation?.loaded")
        for cid in args.characters:
            print("LOADING", cid, flush=True)
            await page.evaluate("id=>window.avatarStudio.refresh(id)", cid)
            await page.wait_for_function("id=>window.avatarSceneInfo?.character===id", arg=cid)
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUT / (cid + "-full.png")), full_page=True)
            # Rendered thumbnails preserve the original asset; no image synthesis.
            await page.locator("#" + ("scene" if cid == "sample_robot" else "cubism-scene")).screenshot(
                path=str(ROOT / "characters" / cid / "concept.png")
            )
            if cid != "sample_robot":
                await page.evaluate("()=>{const s=window.avatarPresentation;s.closeup=true;s.frameView();}")
                await page.wait_for_timeout(700)
            await page.screenshot(path=str(OUT / (cid + "-closed.png")))
            await page.locator('[data-expression="mouth"]').click()
            await page.wait_for_timeout(700)
            await page.screenshot(path=str(OUT / (cid + "-open.png")))
            info = await page.evaluate("window.avatarSceneInfo")
            if cid != "sample_robot":
                assert "ParamMouthOpenY" in info["parameters"] and info["physics"]
                assert await page.evaluate("window.avatarPresentation.current.parameterEvidence.jaw") > 0.8
            await page.locator('[data-expression="auto"]').click()
            await page.locator("#action-preview").select_option("nod")
            await page.wait_for_timeout(700)
            await page.screenshot(path=str(OUT / (cid + "-nod.png")))
            await page.wait_for_timeout(1600)
            await page.evaluate(
                "()=>{const e=window.avatarMotionEvidence;e.speechFrames=0;e.maxMouth=0;e.actionFrames={};}"
            )
            await page.locator("#prompt").fill("请开心地点头欢迎我，只说一句简短的话。")
            await page.locator("#start").click()
            await page.wait_for_function("window.avatarMotionEvidence.speechFrames>5", timeout=150000)
            await page.screenshot(path=str(OUT / (cid + "-speaking.png")))
            await page.wait_for_function("document.querySelector('#cancel').disabled", timeout=150000)
            evidence = await page.evaluate("window.avatarMotionEvidence")
            assert evidence["maxMouth"] > 0.05, evidence
            await page.locator("#open-library").click()
            await page.locator(".voice-card").first.wait_for()
            assert 3 <= await page.locator(".voice-card").count() <= 8
            assert ("CC0" if cid == "sample_robot" else "Live2D") in await page.locator(
                "#asset-provenance"
            ).inner_text()
            await page.screenshot(path=str(OUT / (cid + "-settings.png")), full_page=True)
            await page.locator("#close-library").click()
            r = await page.request.get("http://127.0.0.1:18080/api/characters/" + cid + "/export")
            assert r.ok, await r.text()
            report.append({"id": cid, "scene": info, "motion": evidence, "export_bytes": len(await r.body())})
            print("NATIVE_PASS", cid, json.dumps(evidence), flush=True)
        assert not errors, errors
        (OUT / "report.json").write_text(
            json.dumps({"characters": report, "errors": errors}, ensure_ascii=False, indent=2)
        )
        await browser.close()


asyncio.run(main())
