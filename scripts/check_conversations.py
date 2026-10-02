"""Real-browser persisted conversations: same character threads, role switching, reload."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/browsers"))
OUT = ROOT / "outputs/product-sessions/conversations"
OUT.mkdir(parents=True, exist_ok=True)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--characters", nargs=2, default=["sample_haru", "sample_hiyori"])
A, B = parser.parse_args().characters


async def main():
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto("http://127.0.0.1:18080/?lang=zh-CN")
        await page.wait_for_function(
            "window.avatarPresentation?.loaded && !document.querySelector('#start').disabled"
        )

        async def choose(cid):
            await page.evaluate("id=>window.avatarStudio.refresh(id)", cid)

        async def current():
            return await page.evaluate("window.avatarConversations.current().id")

        async def say(text):
            await page.locator("#prompt").fill(text)
            await page.locator("#start").click()
            await page.wait_for_function(
                "window.avatarDebug.events.some(e=>e.type==='turn_end'&&e.turn===window.avatarDebug.turn)",
                timeout=150000,
            )
            await page.wait_for_function("document.querySelector('#cancel').disabled", timeout=150000)

        await choose(A)
        first = await current()
        await say("请记住，我们这次对话的暗号是蓝松果，只回复记住了。")
        await page.locator("#new-conversation").click()
        await page.wait_for_function("id=>window.avatarConversations.current().id!==id", arg=first)
        second = await current()
        assert await page.locator(".message").count() == 0
        await say("这是一个全新的对话，请简单自我介绍。")
        await choose(B)
        other = await current()
        assert await page.locator(".message").count() == 0
        await choose(A)
        assert await current() == second
        assert "蓝松果" not in await page.locator("#messages").inner_text()
        await page.locator("#conversation-select").select_option(first)
        await page.wait_for_function("id=>window.avatarConversations.current().id===id", arg=first)
        assert "蓝松果" in await page.locator("#messages").inner_text()
        assert "全新的对话" not in await page.locator("#messages").inner_text()
        await page.reload()
        await page.wait_for_function("window.avatarPresentation?.loaded")
        await choose(A)
        assert await current() == first
        assert "蓝松果" in await page.locator("#messages").inner_text()
        await say("我们这次对话的暗号是什么？只说暗号。")
        answer = await page.locator(".assistant .content").last.inner_text()
        assert "蓝松果" in answer, answer
        rows = []
        for cid in [first, second, other]:
            r = await page.request.get("http://127.0.0.1:18080/api/conversations/" + cid)
            rows.append(await r.json())
        assert [len(r["messages"]) for r in rows] == [4, 2, 0]
        assert all(m["status"] == "complete" for r in rows for m in r["messages"])
        await page.screenshot(path=str(OUT / "restored-conversation.png"), full_page=True)
        assert not errors, errors
        (OUT / "report.json").write_text(
            json.dumps(
                {"conversations": rows, "recalled": answer, "errors": errors}, ensure_ascii=False, indent=2
            )
        )
        print("CONVERSATIONS_PASS", first, second, other, flush=True)
        await browser.close()


asyncio.run(main())
