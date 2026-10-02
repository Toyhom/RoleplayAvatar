"""Pinned, resumable range downloads with exact Content-Range and SHA256 validation.

For links with low per-connection throughput. All bytes stay under the configured
model directory. This downloads a complete snapshot, including license files.
"""
import argparse
import hashlib
import json
import os
import shutil
import time
from concurrent import futures
from pathlib import Path

import requests
from huggingface_hub import HfApi, get_hf_file_metadata, hf_hub_download, hf_hub_url

parser = argparse.ArgumentParser()
parser.add_argument("--repo", required=True)
parser.add_argument("--endpoint", default=os.environ.get("HF_ENDPOINT", "https://huggingface.co"))
parser.add_argument("--direct", action="store_true", help="Connect without environment HTTP proxies")
parser.add_argument("--revision", required=True)
parser.add_argument("--root", required=True, type=Path)
parser.add_argument("--connections", type=int, default=32)
parser.add_argument("--files", type=int, default=2)
parser.add_argument("--layout", choices=["full", "diffusers", "anigen-inference"], default="full")
args = parser.parse_args()
if args.direct:
    from huggingface_hub import configure_http_backend
    def direct_session():
        session = requests.Session()
        session.trust_env = False
        return session
    configure_http_backend(backend_factory=direct_session)
    def direct_get(*positional, **kwargs):
        return direct_session().get(*positional, **kwargs)
    requests.get = direct_get
target = args.root / args.repo / args.revision
target.mkdir(parents=True, exist_ok=True)
info = HfApi(endpoint=args.endpoint).model_info(args.repo, revision=args.revision, files_metadata=True, timeout=40)
items = info.siblings
if args.layout == "diffusers":
    # The full Diffusers pipeline includes each component and tokenizer. Alternate
    # single-file exports in the repository root are another serialization of its weights.
    items = [f for f in items if not ("/" not in f.rfilename and f.rfilename.endswith(".safetensors"))]
elif args.layout == "anigen-inference":
    selected = ("ckpts/anigen/ss_flow_duet/", "ckpts/anigen/slat_flow_auto/",
                "ckpts/anigen/ss_dae/ckpts/decoder", "ckpts/anigen/slat_dae/ckpts/decoder",
                "ckpts/dinov2/", "ckpts/dsine/")
    items = [f for f in items if not f.lfs or any(f.rfilename.startswith(p) for p in selected)]
BLOCK = 16 * 1024 * 1024
records = []
verified_dir = target / ".cache/verified"
verified_dir.mkdir(parents=True, exist_ok=True)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8*1024*1024):
            digest.update(block)
    return digest.hexdigest()


def download(item):
    path = target / item.rfilename
    size = item.size
    expected = item.lfs.sha256 if item.lfs else None
    receipt = verified_dir / expected if expected else None
    if path.is_file() and path.stat().st_size == size and (
        not expected or receipt.is_file() or sha256(path) == expected
    ):
        if receipt:
            receipt.write_text(str(size))
        return
    if not expected or size < BLOCK:
        hf_hub_download(args.repo, item.rfilename, revision=args.revision, local_dir=target, endpoint=args.endpoint)
        return
    meta = get_hf_file_metadata(hf_hub_url(args.repo, item.rfilename, revision=args.revision, endpoint=args.endpoint))
    chunks = target / ".cache/ranges" / expected
    chunks.mkdir(parents=True, exist_ok=True)

    def part(index):
        start = index * BLOCK
        end = min(size, start + BLOCK) - 1
        saved = chunks / str(index)
        if saved.is_file() and saved.stat().st_size == end-start+1:
            return
        temp = saved.with_suffix(".partial")
        for attempt in range(30):
            try:
                downloaded = temp.stat().st_size if temp.exists() else 0
                if downloaded == end-start+1:
                    temp.replace(saved)
                    return
                offset = start + downloaded
                began = time.monotonic()
                with requests.get(meta.location, headers={"Range": f"bytes={offset}-{end}"},
                                  stream=True, timeout=(15, 15)) as response:
                    response.raise_for_status()
                    if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {offset}-{end}/{size}":
                        raise ValueError("Incorrect ranged response")
                    with temp.open("ab") as handle:
                        for data in response.iter_content(256*1024):
                            handle.write(data)
                            if time.monotonic()-began > 60:
                                raise requests.Timeout("Slow range; resume on a new connection")
                    if temp.stat().st_size != end-start+1:
                        raise ValueError("Incomplete range")
                    temp.replace(saved)
                return
            except (requests.RequestException, ValueError):
                if attempt == 29:
                    raise
                time.sleep(1)

    count = (size + BLOCK - 1) // BLOCK
    completed = 0
    print("START", item.rfilename, size, flush=True)
    with futures.ThreadPoolExecutor(args.connections) as pool:
        for _ in pool.map(part, range(count)):
            completed += 1
            if completed % 32 == 0:
                print("PROGRESS", item.rfilename, completed, count, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".assembling")
    digest = hashlib.sha256()
    with temp.open("wb") as handle:
        for index in range(count):
            with (chunks / str(index)).open("rb") as source:
                while block := source.read(8*1024*1024):
                    digest.update(block)
                    handle.write(block)
    if digest.hexdigest() != expected:
        raise ValueError("SHA256 mismatch: " + item.rfilename)
    os.replace(temp, path)
    receipt.write_text(str(size))
    shutil.rmtree(chunks)
    print("VERIFIED", item.rfilename, expected, flush=True)


def priority(item):
    if item.size <= BLOCK:
        return 0, item.rfilename
    # Make the chosen inference route usable while unused variants finish downloading.
    preferred = ("ss_flow_duet/", "slat_flow_auto/", "ss_dae/ckpts/decoder", "slat_dae/ckpts/decoder", "dsine/", "dinov2/")
    return (1 if any(p in item.rfilename for p in preferred) else 2), item.rfilename

def resilient_download(item):
    for attempt in range(8):
        try:
            return download(item)
        except (requests.RequestException, OSError) as exc:
            print("RETRY_FILE",item.rfilename,type(exc).__name__,attempt+1,flush=True)
            if attempt == 7:
                raise RuntimeError("Download failed for " + item.rfilename) from None
            time.sleep(5)

with futures.ThreadPoolExecutor(args.files) as pool:
    for _ in pool.map(resilient_download, sorted(items, key=priority)):
        pass
for item in items:
    records.append({"file": item.rfilename, "size": item.size, "sha256": item.lfs.sha256 if item.lfs else None})
(target / ".snapshot-integrity.json").write_text(json.dumps({"repo":args.repo,"revision":args.revision,"layout":args.layout,"files":records}, indent=2))
print("SNAPSHOT_COMPLETE", args.repo, flush=True)
