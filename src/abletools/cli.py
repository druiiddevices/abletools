"""Abletools command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audio import validate_wav
from .manifest import load_manifest
from .midi import validate_midi
from .pack import build_demo_pack, validate_pack


def _validate(path: Path) -> dict[str, object]:
    if path.is_dir():
        return {"type": "pack", "result": validate_pack(path)}
    if path.name == "manifest.json":
        data = load_manifest(path, check_files=True)
        return {"type": "manifest", "files": len(data["files"])}
    if path.suffix.lower() in {".mid", ".midi"}:
        return {"type": "midi", "result": validate_midi(path)}
    if path.suffix.lower() == ".wav":
        return {"type": "wav", "result": validate_wav(path)}
    raise ValueError(f"unsupported path: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abletools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser("demo", help="build a deterministic demo pack")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--seed", type=int, default=1842)
    validate = subparsers.add_parser("validate", help="validate an R1 file or pack")
    validate.add_argument("path", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "demo":
        output = build_demo_pack(args.output, args.seed)
        print(json.dumps({"status": "ok", "pack": str(output), "archive": str(output.with_suffix('.zip'))}))
        return 0
    result = _validate(args.path)
    print(json.dumps({"status": "ok", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
