"""Restore pinned source checkouts; verify existing files before accepting them."""

import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def archive_source(destination, source):
    repo = source["url"].removesuffix(".git").removeprefix("https://github.com/")
    if repo == source["url"] or len(repo.split("/")) != 2:
        raise ValueError("Archive transport requires a GitHub repository")
    url = f"https://codeload.github.com/{repo}/tar.gz/{source['commit']}"
    with urllib.request.urlopen(url, timeout=180) as response:
        raw = response.read()
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = PurePosixPath(member.name).parts[1:]
            if not parts or member.isdir():
                continue
            if not member.isfile() or ".." in parts or PurePosixPath(*parts).is_absolute():
                raise ValueError("Unsupported archive entry: " + member.name)
            relative = Path(*parts)
            content = archive.extractfile(member).read()
            files[relative] = content
    if destination.exists():
        for relative, content in files.items():
            path = destination / relative
            if not path.is_file() or path.is_symlink() or path.read_bytes() != content:
                raise RuntimeError(f"{destination.name}: source differs at {relative}; preserved for review")
    else:
        temporary = destination.with_name(destination.name + ".fetching")
        temporary.mkdir(exist_ok=False)
        for relative, content in files.items():
            path = temporary / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        temporary.rename(destination)
    (destination / ".source-receipt.json").write_text(
        json.dumps(
            {
                "url": source["url"],
                "commit": source["commit"],
                "archive_sha256": hashlib.sha256(raw).hexdigest(),
                "files": {str(p): hashlib.sha256(b).hexdigest() for p, b in files.items()},
            },
            indent=2,
        )
    )


def git_source(destination, source):
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"}

    def git(*args):
        return subprocess.check_output(
            ["git", "-c", f"safe.directory={destination}", "-C", str(destination), *args],
            env=env,
            text=True,
        ).strip()

    if not destination.exists():
        destination.mkdir()
        git("init")
        git("remote", "add", "origin", source["url"])
    if not (destination / ".git").is_dir():
        raise RuntimeError(f"{destination.name}: existing folder is not a Git checkout")
    if {p.name for p in destination.iterdir()} == {".git"}:
        git("fetch", "--depth=1", "origin", source["commit"])
        git("checkout", "--detach", source["commit"])
    if git("rev-parse", "HEAD") != source["commit"] or git("status", "--porcelain"):
        raise RuntimeError(f"{destination.name}: checkout differs or is dirty; preserved for review")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", help="Only these repository names")
    args = parser.parse_args()
    sources = json.loads((ROOT / "configs/upstreams.lock.json").read_text())["repositories"]
    if args.only and set(args.only) - sources.keys():
        parser.error("Unknown repository name")
    (ROOT / "third_party").mkdir(exist_ok=True)
    for name, source in sources.items():
        if args.only and name not in args.only:
            continue
        destination = ROOT / "third_party" / name
        restore = archive_source if source.get("transport") == "archive" else git_source
        restore(destination, source)
        print(name, source["commit"], "verified", flush=True)


if __name__ == "__main__":
    main()
