"""Resumable public auxiliary-weight download with the upstream checksum."""
import argparse
import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

parser = argparse.ArgumentParser()
parser.add_argument("--url", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--md5", required=True)
args = parser.parse_args()
if args.output.is_file():
    digest = hashlib.md5()
    with args.output.open("rb") as handle:
        while block := handle.read(8*1024*1024):
            digest.update(block)
    if digest.hexdigest() == args.md5:
        print("AUXILIARY_MODEL_ALREADY_VERIFIED",args.output.name,flush=True)
        raise SystemExit(0)
response = requests.get(args.url, headers={"Range":"bytes=0-0"}, stream=True, timeout=30)
response.raise_for_status()
if response.status_code != 206:
    raise RuntimeError("The auxiliary download endpoint must support ranges")
total = int(response.headers["Content-Range"].split("/")[-1])
url = response.url
response.close()
parts = args.output.parent / ".cache/ranges" / args.md5
parts.mkdir(parents=True, exist_ok=True)
block = 8*1024*1024


def fetch(index):
    start, end = index*block, min(total,(index+1)*block)-1
    path = parts / str(index)
    if path.is_file() and path.stat().st_size == end-start+1:
        return
    for attempt in range(30):
        offset = path.stat().st_size if path.is_file() else 0
        if offset == end-start+1:
            return
        try:
            began = time.monotonic()
            with requests.get(url,headers={"Range":f"bytes={start+offset}-{end}"},stream=True,timeout=(15,15)) as r:
                r.raise_for_status()
                if r.headers.get("Content-Range") != f"bytes {start+offset}-{end}/{total}":
                    raise ValueError("Incorrect range response")
                with path.open("ab") as handle:
                    for chunk in r.iter_content(256*1024):
                        handle.write(chunk)
                        if time.monotonic()-began>60:
                            raise requests.Timeout()
            if path.stat().st_size == end-start+1:
                return
        except (requests.RequestException, ValueError):
            if attempt == 29:
                raise RuntimeError(f"Unable to complete part {index}") from None
            time.sleep(1)


count = (total+block-1)//block
with ThreadPoolExecutor(24) as pool:
    for i,_ in enumerate(pool.map(fetch,range(count))):
        if i%16==0:
            print("PARTS",i+1,count,flush=True)
digest = hashlib.md5()
temp = args.output.with_suffix(".assembling")
with temp.open("wb") as output:
    for i in range(count):
        data = (parts/str(i)).read_bytes()
        digest.update(data)
        output.write(data)
if digest.hexdigest() != args.md5:
    raise RuntimeError("Auxiliary model checksum mismatch")
os.replace(temp,args.output)
print("AUXILIARY_MODEL_VERIFIED",args.output.name,flush=True)
