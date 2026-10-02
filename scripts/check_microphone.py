"""Browser microphone capture using a real WAV device fixture, real ASR and dialogue."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/browsers"))
p = argparse.ArgumentParser()
p.add_argument("--audio", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--character")
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=True)


async def main():
    errors = []
    result = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--enable-unsafe-swiftshader",
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={args.audio.resolve()}%noloop",
            ],
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 1000}, permissions=["microphone"])
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto("http://127.0.0.1:18080/?lang=zh-CN")
        await page.wait_for_function(
            'window.avatarPresentation?.loaded && !document.querySelector("#microphone").disabled',
            timeout=60000,
        )
        if args.character:
            await page.evaluate("id=>window.avatarStudio.refresh(id)", args.character)
        await page.locator("#microphone").click()
        await page.wait_for_function('window.avatarMicrophone.state==="recording"')
        await page.wait_for_timeout(8200)
        await page.screenshot(path=str(args.output / "recording.png"))
        await page.locator("#microphone").click()
        await page.wait_for_function('document.querySelectorAll(".message.user").length>0', timeout=120000)
        result["transcript"] = await page.locator(".message.user .content").last.inner_text()
        assert result["transcript"].strip()
        await page.wait_for_function("window.avatarDebug.playingSources>0", timeout=120000)
        await page.wait_for_function('document.querySelector("#cancel").disabled', timeout=120000)
        result["reply"] = await page.locator(".message.assistant .content").last.inner_text()
        assert "本轮生成失败" not in result["reply"]
        assert await page.evaluate(
            "window.avatarMicrophone.stream===null && window.avatarMicrophone.context===null"
        )
        await page.screenshot(path=str(args.output / "recognized-conversation.png"))
        before = await page.locator(".message.user").count()
        await page.locator("#microphone").click()
        await page.wait_for_function('window.avatarMicrophone.state==="recording"')
        await page.locator("#cancel-recording").click()
        assert await page.evaluate(
            'window.avatarMicrophone.state==="idle" && window.avatarMicrophone.stream===null'
        )
        assert await page.locator(".message.user").count() == before

        async def delayed(route):
            await asyncio.sleep(1)
            try:
                await route.fulfill(json={"text": "这条取消的识别不应发送"})
            except PlaywrightError as exc:
                result["aborted_route"] = type(exc).__name__

        await page.route("**/api/transcribe", delayed)
        await page.locator("#microphone").click()
        await page.wait_for_function('window.avatarMicrophone.state==="recording"')
        await page.wait_for_timeout(500)
        await page.locator("#microphone").click()
        await page.locator("#cancel-recording").click()
        await page.wait_for_timeout(1400)
        assert await page.locator(".message.user").count() == before
        await page.unroute("**/api/transcribe", delayed)
        await page.evaluate(
            '()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException("denied","NotAllowedError")}}'
        )
        await page.locator("#microphone").click()
        await page.wait_for_function('window.avatarMicrophone.state==="idle"')
        assert "权限" in await page.locator("#microphone-status").inner_text()
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
        assert await page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        assert not errors, errors
        await browser.close()
    result.update(
        page_errors=errors,
        cancel_recording=True,
        cancel_recognition=True,
        permission_denied=True,
        tracks_released=True,
        scope="Real browser getUserMedia/MediaRecorder/decodeAudioData, WAV fake device, real local Whisper and roleplay/TTS. Physical microphone not tested.",
    )
    (args.output / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("MICROPHONE_BROWSER_PASS", json.dumps(result, ensure_ascii=False), flush=True)


asyncio.run(main())
