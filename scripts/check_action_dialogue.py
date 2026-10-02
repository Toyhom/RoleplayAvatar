"""Real model -> spoken sentence -> visible directed actions, including interruption."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/browsers"))
p = argparse.ArgumentParser()
p.add_argument("--character", required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)


async def main():
    errors = []
    wire = []
    report = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))

        def websocket(ws):
            def received(data):
                event = json.loads(data)
                if event.get("type") == "audio":
                    event["data"].pop("pcm_base64", None)
                wire.append(event)

            ws.on("framereceived", received)

        page.on("websocket", websocket)
        await page.goto("http://127.0.0.1:18080/?lang=zh-CN")
        await page.wait_for_function(
            'window.avatarPresentation?.loaded && !document.querySelector("#start").disabled'
        )
        await page.evaluate("id=>window.avatarStudio.refresh(id)", a.character)
        await page.evaluate("()=>{let s=window.avatarPresentation;s.closeup=true;s.frameView();}")
        for name, prompt in [
            ("nod", "请开心地点头答应带我去森林，一句话就好。"),
            ("shake_head", "请摇头拒绝我吃危险蘑菇，一句话就好。"),
            ("bow", "请鞠躬感谢我守护森林，一句话就好。"),
        ]:
            await page.evaluate("window.avatarMotionEvidence.actionFrames={}")
            start = len(wire)
            await page.locator("#prompt").fill(prompt)
            await page.locator("#start").click()
            await page.wait_for_function(
                "name=>(window.avatarMotionEvidence.actionFrames[name]??0)>3", arg=name, timeout=120000
            )
            await page.screenshot(path=str(a.output / f"{name}-playing.png"))
            await page.wait_for_function('document.querySelector("#cancel").disabled', timeout=120000)
            result = await page.evaluate("""()=>({reply:[...document.querySelectorAll('.assistant .content')].at(-1).textContent,
                 actions:window.avatarMotionEvidence.actionFrames,sources:window.avatarDebug.playingSources,
                 frame:window.avatarPresentation.current.frame,preview:window.avatarPresentation.current.actionPreview})""")
            direction = [e["data"] for e in wire[start:] if e.get("type") == "text"]
            assert direction and any(c["name"] == name for d in direction for c in d["actions"])
            assert "〔" in result["reply"] and result["sources"] == 0 and result["frame"] is None
            assert not result["preview"]
            report.append({"expected": name, "direction": direction, "browser": result})
            print("ACTION_DIALOGUE_PASS", name, flush=True)
        await page.locator("#prompt").fill("请先歪头思考，再告诉我今天要去哪里。")
        await page.locator("#start").click()
        await page.wait_for_function("window.avatarDebug.playingSources>0", timeout=120000)
        await page.locator("#cancel").click()
        await page.wait_for_timeout(200)
        cancelled = await page.evaluate("""()=>({sources:window.avatarDebug.playingSources,
              frame:window.avatarPresentation.current.frame,active:window.avatarPresentation.current.actionState.active})""")
        assert cancelled == {"sources": 0, "frame": None, "active": []}, cancelled
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(400)
        assert await page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        await page.screenshot(path=str(a.output / "mobile.png"), full_page=True)
        await browser.close()
    assert not errors, errors
    (a.output / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in wire))
    (a.output / "report.json").write_text(
        json.dumps(
            {"turns": report, "cancelled": cancelled, "errors": errors, "mobile_overflow": False},
            ensure_ascii=False,
            indent=2,
        )
    )
    print("ACTION_BROWSER_PASS", flush=True)


asyncio.run(main())
