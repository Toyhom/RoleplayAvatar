"""Fetch pinned external samples; original assets remain outside source control."""

import concurrent.futures
import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/demo-imports"
config = json.loads((ROOT / "configs/demo-assets.json").read_text())


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        with httpx.Client(timeout=90, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(response.content)
        tmp.replace(path)
    return {
        "url": url,
        "file": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def referenced(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for entry in value:
            yield from referenced(entry)
    elif isinstance(value, dict):
        for key, entry in value.items():
            if key not in {"Name", "FadeInTime", "FadeOutTime"}:
                yield from referenced(entry)


def main():
    records = [download(config["core_url"], ROOT / "third_party/cubism/core.js")]
    if records[0]["sha256"] != config["core_sha256"]:
        raise ValueError("Cubism Core hash changed; review the upstream version before use")
    for index, item in enumerate(config["characters"]):
        folder = OUT / item["id"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "plan.json").write_text(
            json.dumps({"display_name": item["name"], **item}, ensure_ascii=False, indent=2)
        )
        (folder / "request.json").write_text(json.dumps({"seed": 20261001 + index * 100}))
        if item["mode"] == "2d":
            base = f"https://raw.githubusercontent.com/Live2D/CubismWebSamples/{config['cubism_revision']}/Samples/Resources/{item['asset']}/"
            manifest = item["asset"] + ".model3.json"
            records.append(download(base + manifest, folder / "live2d" / manifest))
            data = json.loads((folder / "live2d" / manifest).read_text())
            files = sorted(set(referenced(data["FileReferences"])))
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                records += list(
                    pool.map(
                        lambda name, base=base, folder=folder: download(
                            base + name, folder / "live2d" / name
                        ),
                        files,
                    )
                )
        else:
            base = f"https://raw.githubusercontent.com/mrdoob/three.js/{config['three_revision']}/examples/models/gltf/RobotExpressive/"
            records.append(download(base + "RobotExpressive.glb", folder / "model.glb"))
            records.append(download(base + "README.md", folder / "licenses/RobotExpressive.md"))
        print("FETCHED", item["id"], flush=True)
    licenses = {
        "Live2D-samples.md": f"https://raw.githubusercontent.com/Live2D/CubismWebSamples/{config['cubism_revision']}/LICENSE.md",
        "Live2D-Free-Material.html": "https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html",
        "Live2D-model-terms.html": "https://www.live2d.com/eula/live2d-sample-model-terms_en.html",
        "Live2D-Core.html": "https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html",
    }
    for name, url in licenses.items():
        records.append(download(url, OUT / "licenses" / name))
    (OUT / "downloads.json").write_text(json.dumps(records, indent=2))
    print("DOWNLOADS_VERIFIED", len(records), flush=True)


if __name__ == "__main__":
    main()
