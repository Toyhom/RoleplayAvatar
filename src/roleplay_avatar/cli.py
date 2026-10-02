import argparse
import asyncio
import json
import os
from pathlib import Path

from .adapters import ToneReplayTTS
from .assets import catalog, load_package
from .contracts import SCHEMAS, SpeakRequest
from .session import Session


def main():
    parser = argparse.ArgumentParser(description="Roleplay Avatar engineering tools")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.environ.get("AVATAR_PROJECT_ROOT", Path(__file__).resolve().parents[2])),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("package", type=Path, nargs="?")
    validate.add_argument("--require-assets", action="store_true")
    commands.add_parser("schemas")
    commands.add_parser("doctor", help="Inspect model paths and deployment prerequisites")
    replay = commands.add_parser("replay")
    replay.add_argument("--character", default="dragon_demo")
    replay.add_argument("--output", type=Path, default=Path("outputs/smoke/replay.jsonl"))
    models = commands.add_parser("models", help="List, select and download model presets")
    models.add_argument("action", choices=["list", "recommend", "download", "configure"])
    models.add_argument("selection", nargs="?", default="balanced")
    models.add_argument(
        "--model-root", type=Path, default=Path(os.environ.get("AVATAR_MODEL_ROOT", "models"))
    )
    models.add_argument("--endpoint", default=os.environ.get("HF_ENDPOINT", "https://huggingface.co"))
    models.add_argument("--mirror", action="store_true", help="Use https://hf-mirror.com")
    models.add_argument("--token-env", help="Read an explicitly selected download credential")
    models.add_argument("--creation", action="store_true")
    models.add_argument("--dry-run", action="store_true")
    models.add_argument("--vram-gib", type=float, default=0)
    models.add_argument("--gpus", type=int, default=1)
    models.add_argument("--output", type=Path, default=Path("configs/models.local.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "doctor":
        from .doctor import inspect
        print(json.dumps(inspect(), indent=2))
    elif args.command == "models":
        from .model_catalog import catalog as model_catalog
        from .model_catalog import download, download_plan, preset_config, recommend

        if args.action == "list":
            print(json.dumps(model_catalog(), ensure_ascii=False, indent=2))
        elif args.action == "recommend":
            print(json.dumps(recommend(args.vram_gib, args.gpus), indent=2))
        elif args.action == "configure":
            result = preset_config(args.selection, args.model_root, args.creation)
            if args.output.exists():
                raise SystemExit(f"Configuration exists: {args.output}. Choose a new --output path.")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            print(f"Set AVATAR_MODELS_CONFIG={args.output.resolve()}")
        else:
            plan = download_plan(
                args.selection,
                args.model_root,
                "https://hf-mirror.com" if args.mirror else args.endpoint,
                args.creation,
            )
            print(json.dumps(plan, indent=2), flush=True)
            if not args.dry_run:
                for entry in plan:
                    print("Downloading " + entry["id"], flush=True)
                    print(download(entry, token_env=args.token_env), flush=True)
    elif args.command == "validate":
        paths = (
            [args.package]
            if args.package
            else sorted(
                p for p in (root / "characters").iterdir() if p.is_dir() and (p / "profile.json").is_file()
            )
        )
        for path in paths:
            package = load_package(path, args.require_assets)
            print(f"{package.profile.character_id}: contract valid ({package.profile.package_status})")
    elif args.command == "schemas":
        directory = root / "schemas"
        directory.mkdir(exist_ok=True)
        for name, model in SCHEMAS.items():
            (directory / f"{name}.schema.json").write_text(
                json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        print(f"Exported {len(SCHEMAS)} schemas")
    else:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)

        async def run():
            with output.open("w", encoding="utf-8") as handle:

                async def send(event):
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")

                session = Session(send, catalog(root / "fixtures/characters_m0"), ToneReplayTTS(paced=False))
                await session.start(
                    SpeakRequest(
                        type="speak",
                        turn_id="smoke_001",
                        character_id=args.character,
                        text="请介绍一下你自己",
                    )
                )
                await session.task

        asyncio.run(run())
        events = [json.loads(line) for line in output.read_text().splitlines()]
        if not events or events[-1]["type"] != "turn_end":
            raise SystemExit("Replay failed; inspect the event log")
        print(f"Saved {len(events)} diagnostic events to {output}")


if __name__ == "__main__":
    main()
