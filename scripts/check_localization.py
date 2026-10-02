"""Exercise each UI language and responsive layout against a running studio."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/browsers"))
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--url", default="http://127.0.0.1:18080")
p.add_argument("--output", type=Path, default=ROOT / "outputs/localization")
args = p.parse_args()


async def main():
    args.output.mkdir(parents=True, exist_ok=True)
    errors, results = [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=["--no-sandbox", "--enable-unsafe-swiftshader"])
        for locale, label in [
            ("en", "Create character"),
            ("zh-CN", "创建角色"),
            ("ja", "キャラクターを作成"),
        ]:
            context = await browser.new_context(viewport={"width": 1440, "height": 1000})
            page = await context.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            await page.goto(args.url.rstrip("/") + "/?lang=" + locale)
            await page.wait_for_function("window.avatarPresentation?.loaded", timeout=90000)
            assert await page.locator("html").get_attribute("lang") == locale
            assert label in await page.locator("#open-create").inner_text()
            assert await page.locator("#new-conversation").is_disabled()
            conversation = await page.evaluate("window.avatarConversations.current().id")
            # Language changes retain the actual context and unsent text.
            await page.locator("#prompt").fill("Unsent draft — 未送信")
            target = "ja" if locale != "ja" else "en"
            await page.locator("#language").select_option(target)
            await page.wait_for_function(
                "window.avatarPresentation?.loaded && document.documentElement.lang === '" + target + "'",
                timeout=90000,
            )
            assert await page.evaluate("window.avatarConversations.current().id") == conversation
            assert await page.locator("#prompt").input_value() == "Unsent draft — 未送信"
            await page.locator("#language").select_option(locale)
            await page.wait_for_function(
                "window.avatarPresentation?.loaded && document.documentElement.lang === '" + locale + "'",
                timeout=90000,
            )
            await page.screenshot(path=str(args.output / f"{locale}-desktop.png"))
            export = await page.request.get(
                urljoin(args.url, await page.locator("#export-conversation").get_attribute("href"))
            )
            assert export.status == 200
            assert (await export.json())["conversation"]["id"] == conversation
            await page.locator("#open-create").click()
            await page.locator("#creation-source").select_option("live2d")
            assert await page.locator("#character-image").get_attribute("accept") == ".zip"
            await page.locator("#creation-mode").select_option("3d")
            assert await page.locator("#creation-source").input_value() == "image"
            await page.screenshot(path=str(args.output / f"{locale}-creation.png"))
            await page.locator("#close-create").click()
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.wait_for_timeout(300)
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            await page.screenshot(path=str(args.output / f"{locale}-mobile.png"), full_page=True)
            results.append(
                {"locale": locale, "desktop": True, "mobile": True, "context_preserved": True, "export": True}
            )
            await context.close()
        await browser.close()
    report = {"languages": results, "errors": errors}
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    assert not errors, errors
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
