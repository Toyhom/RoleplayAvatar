"""Real browser playback, deformation and interruption; requires live demo services."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/browsers"))
parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:18080")
parser.add_argument("--characters", nargs="+", help="Character IDs; default: current library")
parser.add_argument("--modes", nargs="+", choices=["2d", "3d"], default=["2d", "3d"])
parser.add_argument("--output", type=Path, default=ROOT / "outputs/browser-validation")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)


async def main():
    results, errors = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(args.url.rstrip("/") + "/?lang=zh-CN")
        await page.wait_for_function("window.avatarSceneInfo && !document.querySelector('#start').disabled")
        services = await page.evaluate("fetch('/api/services').then(r=>r.json())")
        assert services["mode"] == "live", services
        library = await page.evaluate("fetch('/api/characters').then(r=>r.json())")
        capabilities = {c["profile"]["character_id"]: c["capabilities"] for c in library}
        available_modes = {c["profile"]["character_id"]: c["profile"]["presentation_modes"] for c in library}
        characters = args.characters or list(capabilities)
        assert characters, "Create at least one character first"
        for character in characters:
            for mode in args.modes:
                if mode not in available_modes[character]:
                    continue

                async def delayed_details(route):
                    await asyncio.sleep(0.4)
                    await route.continue_()

                details_url = args.url + f"/api/characters/{character}"
                await page.route(details_url, delayed_details)
                await page.locator(f'[data-id="{character}"]').click()
                assert await page.locator("#start").is_disabled(), "Selection must immediately block sending"
                await page.wait_for_function(
                    "id=>window.avatarSceneInfo?.character===id && !document.querySelector('#start').disabled",
                    arg=character,
                )
                await page.unroute(details_url, delayed_details)
                await page.evaluate("mode=>window.avatarPresentation.switch(mode)", mode)
                await page.wait_for_function(
                    "window.avatarPresentation.loaded && !document.querySelector('#start').disabled"
                )
                await page.locator("#prompt").fill("请用一句简短的话介绍你自己。")
                await page.locator("#start").click()
                await page.wait_for_function("window.avatarDebug.playingSources>0", timeout=180000)
                await page.wait_for_function("window.avatarMotionEvidence.speechFrames>8", timeout=30000)
                await page.screenshot(path=str(args.output / f"{character}-{mode}.png"))
                await page.wait_for_function("document.querySelector('#cancel').disabled", timeout=180000)
                result = await page.evaluate("""()=>({scene:window.avatarSceneInfo,
                    motion:window.avatarMotionEvidence,firstAudioArrivalMs:window.avatarDebug.firstAudioMs,
                    remainingSources:window.avatarDebug.playingSources,fps:window.avatarRenderFps,
                    reply:[...document.querySelectorAll('.assistant .content')].at(-1).textContent})""")
                (args.output / f"{character}-{mode}.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2)
                )
                assert result["remainingSources"] == 0, result
                assert result["motion"]["speechFrames"] > 8
                assert result["motion"]["maxJointDelta"] > 0, result
                if "face" in capabilities[character]["active_streams"]:
                    assert result["motion"]["maxMouth"] > 0.01
                assert "本轮生成失败" not in result["reply"]
                results.append(result)
                print("BROWSER_CHARACTER_PASS", character, mode, flush=True)
        await page.locator("#prompt").fill("请讲一个稍长的探险故事。")
        await page.locator("#start").click()
        await page.wait_for_function("window.avatarDebug.playingSources>0", timeout=180000)
        switched = {"skipped": "Single presentation mode requested or supported"}
        if len(args.modes) > 1 and len(available_modes[character]) > 1:
            switched = await page.evaluate("""async()=>{
                const stage=window.avatarPresentation, from=stage.kind;
                const before=window.avatarDebug.turn;
                await stage.switch(from==='2d'?'3d':'2d');
                return {from,to:stage.kind,before,after:window.avatarDebug.turn,
                        sources:window.avatarDebug.playingSources,loaded:stage.loaded};
            }""")
            assert switched["loaded"] and switched["before"] == switched["after"] and switched["sources"] > 0
        cancellation = await page.evaluate("""()=>{const t=performance.now();
            document.querySelector('#cancel').click();
            return {handlerMs:performance.now()-t,sources:window.avatarDebug.playingSources,
                    turn:window.avatarDebug.turn};}""")
        assert cancellation["sources"] == 0 and cancellation["turn"] is None
        await page.locator("#prompt").fill("请说你好。")
        await page.locator("#start").click()
        await page.wait_for_function("window.avatarDebug.playingSources>0", timeout=180000)
        await page.wait_for_function("document.querySelector('#cancel').disabled", timeout=180000)
        assert "本轮生成失败" not in await page.locator(".assistant .content").last.inner_text()
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        await browser.close()
    report = {
        "characters": results,
        "cancel": cancellation,
        "switch_while_speaking": switched,
        "page_errors": errors,
        "replacement_after_cancel": "passed",
        "mobile_no_horizontal_overflow": True,
        "rendering": "Chromium software WebGL on server; not a client GPU FPS benchmark",
        "audio_scope": "AudioContext scheduled and drained; physical speaker not measured",
    }
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("BROWSER_LIVE_PASS", flush=True)


asyncio.run(main())
