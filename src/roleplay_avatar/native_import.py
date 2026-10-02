"""Validate and stage user-supplied Cubism resources without executing archive content."""

import hashlib
import io
import json
import shutil
import stat
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image

from .assets import cubism_files
from .creation import write_json
from .languages import LANGUAGES

ALLOWED = {
    ".json",
    ".moc3",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".wav",
    ".mp3",
    ".txt",
    ".md",
    ".exp3",
    ".motion3",
}


def extract_live2d(raw, destination, model_entry=None):
    if len(raw) > 128_000_000:
        raise ValueError("Live2D ZIP 最大 128 MB")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > 4096 or sum(e.file_size for e in entries) > 512_000_000:
            raise ValueError("资源包解压大小或文件数量超限")
        seen = set()
        for entry in entries:
            name = entry.filename
            if name.startswith("__MACOSX/") or PurePosixPath(name).name == ".DS_Store":
                continue
            path = PurePosixPath(name)
            if "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts or "\x00" in name:
                raise ValueError("资源包包含不安全路径")
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise ValueError("资源包不支持符号链接或加密文件")
            if entry.is_dir():
                continue
            if name.lower() in seen:
                raise ValueError("资源包存在重复文件名")
            seen.add(name.lower())
            license_document = "licenses" in {
                part.lower() for part in path.parts
            } and path.suffix.lower() in {".html", ".pdf"}
            if (
                path.suffix.lower() not in ALLOWED
                and path.name.lower() not in {"license", "notice"}
                and not license_document
            ):
                raise ValueError("请上传模型资源包，不包含脚本、运行程序或编辑器工程：" + path.name)
            if entry.file_size > 128_000_000 or entry.file_size > max(1, entry.compress_size) * 300:
                raise ValueError("资源包文件大小或压缩比例异常")
            target = destination / Path(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    manifests = sorted(destination.rglob("*.model3.json"))
    if model_entry:
        manifests = [p for p in manifests if p.relative_to(destination).as_posix() == model_entry]
    if len(manifests) != 1:
        raise ValueError("资源包需包含一个 .model3.json；多个模型时请指定 model_entry")
    manifest = manifests[0]
    relative = "live2d/" + manifest.relative_to(destination).as_posix()
    declared = cubism_files(destination.parent, relative)
    if any(not (destination.parent / name).is_file() for name in declared):
        raise ValueError("资源包缺少模型声明引用的文件")
    data = json.loads(manifest.read_text())
    moc = manifest.parent / data["FileReferences"]["Moc"]
    if moc.read_bytes()[:4] != b"MOC3":
        raise ValueError("无效的 Cubism moc3 文件")
    textures = data["FileReferences"].get("Textures", [])
    if not isinstance(textures, list) or not textures or not all(isinstance(t, str) for t in textures):
        raise ValueError("模型缺少纹理")
    for texture in textures:
        with Image.open(manifest.parent / texture) as im:
            if im.width * im.height > 64_000_000:
                raise ValueError("纹理分辨率过大")
            im.verify()
    return relative, {
        "files": len(declared),
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "moc_sha256": hashlib.sha256(moc.read_bytes()).hexdigest(),
        "lip_sync_parameters": next(
            (g.get("Ids", []) for g in data.get("Groups", []) if g.get("Name") == "LipSync"), []
        ),
    }


def create_native_job(store, raw, description, voice_candidates=5, model_entry=None, locale="zh-CN"):
    if locale not in LANGUAGES:
        raise ValueError("Unsupported character language")
    if not 2 <= len(description.strip()) <= 1500:
        raise ValueError("请填写 2 至 1500 字的角色与声音描述")
    if not 3 <= voice_candidates <= 8:
        raise ValueError("声线候选数量为 3 至 8")
    job_id = uuid.uuid4().hex
    folder = store.jobs / job_id
    try:
        manifest, report = extract_live2d(raw, folder / "live2d", model_entry)
        write_json(
            folder / "request.json",
            {
                "id": job_id,
                "source": "live2d",
                "presentation": "2d",
                "description": description,
                "locale": locale,
                "seed": int(time.time()) % (2**31),
                "voice_candidates": voice_candidates,
                "native_manifest": manifest,
                "import_report": report,
            },
        )
        write_json(
            folder / "status.json",
            {
                "id": job_id,
                "state": "queued",
                "stage": "queued",
                "progress": 0,
                "created_at": time.time(),
                "updated_at": time.time(),
            },
        )
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    store.submit(folder)
    return store.get(job_id)
