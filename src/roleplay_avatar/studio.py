"""Creation, library editing and portable export HTTP routes."""

import asyncio
import hashlib
import io
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .assets import cubism_files, load_package
from .creation import CreationRequest, CreationStore, read_json, write_json
from .languages import Locale
from .native_import import create_native_job


class CharacterEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=50)
    persona: str = Field(min_length=10, max_length=2400)


class VoiceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate: int = Field(ge=1, le=100)


def studio_routes(root, refresh):
    root = Path(root)
    store = CreationStore(root)
    router = APIRouter(prefix="/api")
    lock = asyncio.Lock()

    def folder(cid):
        if not re.fullmatch(r"(?:char_[a-f0-9]{16}|sample_[a-z0-9_]+)", cid):
            raise HTTPException(404, "unknown character")
        path = root / "characters" / cid
        if not (path / "profile.json").is_file():
            raise HTTPException(404, "unknown character")
        return path

    @router.get("/studio")
    def config():
        return {
            "creation_available": store.runner in {"gpuq", "local"},
            "max_image_mb": 10,
            "stages": [
                "understanding",
                "illustrating",
                "modeling",
                "landmarking",
                "refining",
                "rigging",
                "voicing",
                "packaging",
            ],
        }

    @router.post(
        "/characters/import-live2d",
        status_code=202,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
            }
        },
    )
    async def import_live2d(
        request: Request, description: str, voice_candidates: int = 5, model_entry: str | None = None,
        locale: Locale = "zh-CN",
    ):
        if store.runner not in {"gpuq", "local"}:
            raise HTTPException(503, "角色创建工作进程尚未配置")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 128_000_000:
                raise HTTPException(413, "Live2D ZIP 最大 128 MB")
        async with lock:
            if (
                len(
                    [
                        j
                        for j in await asyncio.to_thread(store.list)
                        if j["state"] in {"queued", "running", "submission_error"}
                    ]
                )
                >= 3
            ):
                raise HTTPException(429, "已有三个创建任务")
            try:
                return await asyncio.to_thread(
                    create_native_job, store, bytes(raw), description, voice_candidates, model_entry, locale
                )
            except (
                ValueError,
                zipfile.BadZipFile,
                KeyError,
                OSError,
                TypeError,
                AttributeError,
                Image.DecompressionBombError,
            ) as exc:
                raise HTTPException(422, str(exc)) from None
            except Exception:  # noqa: BLE001 -- scheduler failures must not expose local paths
                raise HTTPException(503, "任务提交未确认，请检查生成列表。请勿重复提交。") from None

    @router.get("/creations")
    def creations():
        return store.list()

    @router.post(
        "/creations",
        status_code=202,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": CreationRequest.model_json_schema()}},
            }
        },
    )
    async def create(request: Request):
        if store.runner not in {"gpuq", "local"}:
            raise HTTPException(503, "角色生成服务未配置")
        # Enforce size while consuming, including chunked requests without Content-Length.
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 14_100_000:
                raise HTTPException(413, "图片不得超过 10 MB")
        try:
            payload = CreationRequest.model_validate_json(content)
        except ValidationError:
            raise HTTPException(422, "请上传有效图片，并填写 2 至 1500 字的角色描述") from None
        async with lock:
            jobs = await asyncio.to_thread(store.list)
            active = [j for j in jobs if j["state"] in {"queued", "running", "submission_error"}]
            if len(active) >= 3:
                raise HTTPException(429, "已有三个生成任务，请等待或取消后再创建")
            try:
                return await asyncio.to_thread(store.create, payload)
            except (ValueError, OSError):
                raise HTTPException(422, "无法读取图片，请检查格式、分辨率与大小") from None
            except Exception:  # noqa: BLE001 -- submission failures must not expose scheduler details
                raise HTTPException(503, "任务提交未确认，请检查生成列表。请勿重复提交。") from None

    @router.get("/creations/{job_id}")
    def creation(job_id: str):
        try:
            return store.get(job_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, "unknown creation") from None

    @router.post("/creations/{job_id}/cancel")
    async def cancel(job_id: str):
        try:
            return await asyncio.to_thread(store.cancel, job_id)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, "unknown creation") from None

    @router.post("/creations/{job_id}/retry", status_code=202)
    async def retry(job_id: str):
        async with lock:
            try:
                return await asyncio.to_thread(store.retry, job_id)
            except FileNotFoundError:
                raise HTTPException(404, "unknown creation") from None
            except ValueError:
                raise HTTPException(409, "上一个任务尚未退出，暂时不能重试") from None

    @router.get("/creations/{job_id}/files/{name}")
    def creation_file(job_id: str, name: str):
        if name not in {"input.png", "concept.png", "preview.png"}:
            raise HTTPException(404, "unknown file")
        try:
            path = store.folder(job_id) / name
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, "unknown creation") from None
        if not path.is_file():
            raise HTTPException(404, "file not ready")
        return FileResponse(path)

    @router.get("/characters/{cid}/studio")
    def details(cid: str):
        path = folder(cid)
        return {
            "plan": read_json(path / "character.json"),
            "voices": read_json(path / "voice/candidates.json"),
            "provenance": read_json(path / "provenance.json"),
        }

    @router.patch("/characters/{cid}")
    async def edit(cid: str, payload: CharacterEdit):
        async with lock:
            path = folder(cid)
            profile = read_json(path / "profile.json")
            profile.update(payload.model_dump())
            write_json(path / "profile.json", profile)
            plan = read_json(path / "character.json")
            plan.update(payload.model_dump())
            write_json(path / "character.json", plan)
            refresh()
        return profile

    @router.post("/characters/{cid}/voice")
    async def select_voice(cid: str, payload: VoiceSelection):
        async with lock:
            path = folder(cid)
            voices = read_json(path / "voice/candidates.json")
            selected = next((v for v in voices["candidates"] if v["candidate"] == payload.candidate), None)
            if selected is None:
                raise HTTPException(404, "Unknown voice candidate")
            raw = (path / f"voice/candidate_{payload.candidate}.wav").read_bytes()
            if hashlib.sha256(raw).hexdigest() != selected["sha256"]:
                raise HTTPException(409, "声线文件校验失败")
            # References are immutable, so in-flight speech keeps its original file.
            voice = read_json(path / "voice_profile.json")
            voice.update(
                reference_audio=f"voice/candidate_{payload.candidate}.wav",
                reference_sha256=selected["sha256"],
                design_prompt=selected["prompt"],
            )
            write_json(path / "voice_profile.json", voice)
            voices["selected"] = payload.candidate
            voices["selection_method"] = "user"
            write_json(path / "voice/candidates.json", voices)
            refresh()
        return voices

    @router.get("/characters/{cid}/voice/{candidate}")
    def voice(cid: str, candidate: int):
        candidates = read_json(folder(cid) / "voice/candidates.json")["candidates"]
        if candidate not in {v["candidate"] for v in candidates}:
            raise HTTPException(404, "unknown candidate")
        return FileResponse(folder(cid) / f"voice/candidate_{candidate}.wav", media_type="audio/wav")

    @router.get("/characters/{cid}/export")
    async def export(cid: str):
        path = folder(cid)

        def build():
            package = load_package(path, require_assets=True)
            output = io.BytesIO()
            allowed = {
                "model.glb",
                "character.json",
                "generation.json",
                "preview.png",
                "concept.png",
                "input.png",
                "profile.json",
                "capabilities.json",
                "rig_map.json",
                "face_map.json",
                "motion_manifest.json",
                "voice_profile.json",
                "provenance.json",
                "qa_report.json",
            }
            if package.profile.renderer_2d == "cubism":
                allowed.update(cubism_files(path, package.profile.live2d_model))
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for item in sorted(path.rglob("*")):
                    relative = item.relative_to(path)
                    if (
                        item.is_file()
                        and not item.is_symlink()
                        and (
                            str(relative) in allowed
                            or relative.parts[0] in {"voice", "licenses"}
                            or str(relative)
                            in {
                                "puppet/portrait.png",
                                "puppet/rig.json",
                                "puppet/mouth-atlas.png",
                                "puppet/mouth-generation.json",
                            }
                        )
                    ):
                        archive.write(item, str(Path(cid) / relative))
            output.seek(0)
            return output

        async with lock:
            output = await asyncio.to_thread(build)
        return StreamingResponse(
            output,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{cid}.zip"'},
        )

    return router
