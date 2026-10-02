"""Run a configured local engine inside a service group or GPU allocation."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roleplay_avatar.inference import engine_config, fingerprint, start


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", type=int, default=18110)
    parser.add_argument("--role", default="roleplay")
    parser.add_argument("--config-sha256", help="Expected inference configuration when queued")
    args = parser.parse_args()
    config = engine_config(args.role, overrides={"port": args.port})
    if args.config_sha256 and fingerprint(args.role, config=config, model=args.model) != args.config_sha256:
        raise ValueError("Inference configuration changed after submission; submit the updated configuration")
    start(args.role, config=config, model=args.model)


if __name__ == "__main__":
    main()
