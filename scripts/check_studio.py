"""Exercise the real upload UI, durable worker, character settings and portable export."""

import argparse
import asyncio
import hashlib
import io
import json
import os
import time
import zipfile
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".cache/browsers"))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:18080")
parser.add_argument("--input", type=Path)
parser.add_argument("--description-file", type=Path)
parser.add_argument("--job", help="Resume validation without submitting again")
parser.add_argument("--seed", type=int, help="Pin the creation seed for reproducible UI validation")
parser.add_argument("--output", type=Path, default=ROOT / "outputs/studio-validation")
parser.add_argument("--timeout", type=int, default=7200)
args = parser.parse_args()
if not args.job and not (args.input and args.description_file):
    parser.error("Supply --job, or both --input and --description-file")
args.output.mkdir(parents=True, exist_ok=True)


def save(name, value):
    (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))


async def browser_start(p):
    return await p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])


async def main():
    job_id = args.job
    errors = []
    async with async_playwright() as playwright:
        if not job_id:
            browser = await browser_start(playwright)
            page = await browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            if args.seed is not None:

                async def seed_request(route):
                    if route.request.method == "POST":
                        payload = route.request.post_data_json
                        payload["seed"] = args.seed
                        await route.continue_(post_data=json.dumps(payload, ensure_ascii=False))
                    else:
                        await route.continue_()

                await page.route("**/api/creations", seed_request)
            await page.goto(args.url.rstrip("/") + "/?lang=zh-CN")
            await page.locator("#open-create").click()
            await page.locator("#character-image").set_input_files(str(args.input.resolve()))
            await page.locator("#character-brief").fill(args.description_file.read_text())
            await page.wait_for_function("!document.querySelector('#upload-preview').hidden")
            async with page.expect_response(
                lambda r: r.url.endswith("/api/creations") and r.request.method == "POST", timeout=60000
            ) as pending:
                await page.locator("#create-submit").click()
            response = await pending.value
            assert response.status == 202, await response.text()
            job = await response.json()
            job_id = job["id"]
            save("submitted.json", job)
            await page.screenshot(path=str(args.output / "submitted.png"), full_page=True)
            await browser.close()
            print("STUDIO_SUBMITTED", job_id, flush=True)
        began = time.monotonic()
        last_stage = None
        async with httpx.AsyncClient(trust_env=False, timeout=60) as client:
            while True:
                response = await client.get(args.url + "/api/creations/" + job_id)
                response.raise_for_status()
                job = response.json()
                if (job["state"], job["stage"]) != last_stage:
                    print("STUDIO_PROGRESS", job["state"], job["stage"], flush=True)
                    last_stage = job["state"], job["stage"]
                save("latest-job.json", job)
                if job["state"] == "ready":
                    break
                if job["state"] in {"failed", "cancelled", "submission_error"}:
                    raise RuntimeError(f"Creation {job_id}: {job['state']} at {job['stage']}")
                if time.monotonic() - began > args.timeout:
                    raise TimeoutError(f"Worker remains active; resume this check with --job {job_id}")
                await asyncio.sleep(10)
            cid = job["character_id"]
            original = (await client.get(args.url + "/api/characters/" + cid)).json()
            browser = await browser_start(playwright)
            page = await browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(args.url.rstrip("/") + "/?lang=zh-CN")
            await page.wait_for_function("window.avatarStudio")
            await page.evaluate("id => window.avatarStudio.refresh(id)", cid)
            await page.wait_for_function("id => window.avatarSceneInfo?.character === id", arg=cid)
            await page.screenshot(path=str(args.output / "generated-character.png"), full_page=True)
            await page.locator("#open-library").click()
            await page.locator(".voice-card").first.wait_for()
            await page.locator("#edit-name").fill(original["profile"]["display_name"] + "·验收")
            await page.locator("#save-persona").click()
            await page.wait_for_function(
                "document.querySelector('#library-feedback').textContent.includes('已保存')"
            )
            changed = (await client.get(args.url + "/api/characters/" + cid)).json()
            assert changed["profile"]["display_name"].endswith("·验收")
            await page.locator("#edit-name").fill(original["profile"]["display_name"])
            await page.locator("#save-persona").click()
            await page.wait_for_function("!document.querySelector('#save-persona').disabled")
            voices = (await client.get(args.url + f"/api/characters/{cid}/studio")).json()["voices"]
            first_choice = voices["selected"]
            candidate = first_choice % 3 + 1
            async with page.expect_response(
                lambda r: r.url.endswith(f"/characters/{cid}/voice") and r.request.method == "POST"
            ):
                await page.locator(".voice-card").nth(candidate - 1).locator(".voice-select").click()
            selected = (await client.get(args.url + "/api/characters/" + cid)).json()["voice_profile"]
            sample = await client.get(args.url + f"/assets/{cid}/reference.wav")
            assert hashlib.sha256(sample.content).hexdigest() == selected["reference_sha256"]
            for i in (1, 2, 3):
                sample = await client.get(args.url + f"/api/characters/{cid}/voice/{i}")
                assert sample.status_code == 200 and sample.content[:4] == b"RIFF"
            await client.post(args.url + f"/api/characters/{cid}/voice", json={"candidate": first_choice})
            await page.screenshot(path=str(args.output / "character-settings.png"), full_page=True)
            exported = await client.get(args.url + f"/api/characters/{cid}/export")
            exported.raise_for_status()
            (args.output / "character.zip").write_bytes(exported.content)
            with zipfile.ZipFile(io.BytesIO(exported.content)) as package:
                names = package.namelist()
                required_files = [
                    "profile.json",
                    "capabilities.json",
                    "rig_map.json",
                    "face_map.json",
                    "motion_manifest.json",
                    "voice_profile.json",
                    "provenance.json",
                    "qa_report.json",
                ]
                if "3d" in original["profile"]["presentation_modes"]:
                    required_files.append("model.glb")
                if "2d" in original["profile"]["presentation_modes"]:
                    required_files += [
                        "puppet/portrait.png",
                        "puppet/rig.json",
                        "puppet/mouth-atlas.png",
                        "puppet/mouth-generation.json",
                    ]
                for required in required_files:
                    assert cid + "/" + required in names
                assert all(name.startswith(cid + "/") and ".." not in Path(name).parts for name in names)
                assert not any(name.endswith((".env", ".log")) for name in names)
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.screenshot(path=str(args.output / "settings-mobile.png"), full_page=True)
            assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            await browser.close()
            assert not errors, errors
            save(
                "report.json",
                {
                    "job_id": job_id,
                    "character_id": cid,
                    "upload_ui": "passed" if not args.job else "resumed",
                    "generated_package": "passed",
                    "persona_edit_restore": "passed",
                    "voice_selection_hash": "passed",
                    "three_audio_candidates": "passed",
                    "export": names,
                    "mobile_overflow": False,
                    "page_errors": errors,
                },
            )
            print("STUDIO_PASS", cid, flush=True)


asyncio.run(main())
