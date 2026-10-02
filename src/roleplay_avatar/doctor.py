"""Read-only configuration diagnostics, suitable for users and setup assistants."""

import json
import os
import shutil
import sys
from pathlib import Path

from .models import agent_config, configuration, model_path


def checkpoint_files(path):
    """Check local snapshot references without loading weights or accessing the network."""
    path = Path(path)
    if not path.exists():
        return ["Model path is missing"]
    if path.is_file():
        return [] if path.stat().st_size else ["Model file is empty"]
    problems = []
    directories = [path]
    try:
        pipeline = path / "model_index.json"
        if pipeline.is_file():
            for name, value in json.loads(pipeline.read_text()).items():
                if name.startswith("_") or not isinstance(value, list) or len(value) != 2 or not value[1]:
                    continue
                component = path / name
                if not component.is_dir():
                    problems.append(f"Missing pipeline component: {name}")
                elif any(word in value[1].lower() for word in ("model", "autoencoder", "unet")):
                    directories.append(component)
        for directory in directories:
            indexes = sorted(directory.glob("*.index.json"))
            for index in indexes:
                weight_map = json.loads(index.read_text()).get("weight_map", {})
                for name in sorted(set(weight_map.values())):
                    file = directory / name
                    if not file.is_file() or not file.stat().st_size:
                        problems.append(f"Missing checkpoint shard: {file.relative_to(path)}")
            if directory != path and not indexes and not any(
                f.is_file() and f.stat().st_size
                for pattern in ("*.safetensors", "*.bin")
                for f in directory.glob(pattern)
            ):
                problems.append(f"Missing component weights: {directory.relative_to(path)}")
        receipt = path / ".avatar-download.json"
        if receipt.is_file():
            for entry in json.loads(receipt.read_text()).get("files", []):
                file = path / entry["file"]
                if not file.is_file():
                    problems.append(f"Missing downloaded file: {entry['file']}")
                elif entry.get("size") is not None and file.stat().st_size != entry["size"]:
                    problems.append(f"Incomplete downloaded file: {entry['file']}")
    except (OSError, ValueError, TypeError, KeyError) as error:
        problems.append(f"Cannot inspect checkpoint metadata: {type(error).__name__}")
    return problems


def inspect():
    config = configuration()
    checks = [{"name": "Python", "ok": sys.version_info[:2] == (3, 11), "value": sys.version.split()[0]}]
    for command in ["node", "npm", "ffmpeg", "sox"]:
        checks.append({"name": command, "ok": bool(shutil.which(command)), "value": shutil.which(command)})
    for role in config.get("models", {}):
        entry = config["models"][role]
        if entry.get("adapter") == "api":
            continue
        path = model_path(role)
        problems = checkpoint_files(path)
        checks.append({"name": "model:" + role, "ok": not problems, "value": str(path), "problems": problems})
    for role in ["roleplay", "performance_director", "initiative", "character_design", "voice_direction"]:
        agent = agent_config(role)
        key_name = agent.get("api_key_env", "AVATAR_LLM_API_KEY")
        present = bool(os.environ.get(key_name))
        checks.append(
            {
                "name": "agent:" + role,
                "ok": agent["backend"] == "local" or not agent.get("require_key", False) or present,
                "value": {
                    "protocol": agent["backend"],
                    "model": agent["model"],
                    "key_variable": key_name,
                    "key_present": present,
                },
            }
        )
    for role in config.get("inference", {}):
        from .inference import launch_plan

        try:
            plan = launch_plan(role, check=True)
            checks.append({"name": "inference:" + role, "ok": True,
                           "value": {"engine": plan["engine"], "health_url": plan["health_url"]}})
        except (ValueError, OSError) as error:
            checks.append({"name": "inference:" + role, "ok": False, "value": str(error)})
    return {"checks": checks, "ready": all(c["ok"] for c in checks)}
