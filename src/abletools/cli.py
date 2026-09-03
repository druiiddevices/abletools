"""Abletools command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audio import validate_wav
from .manifest import load_manifest
from .midi import validate_midi
from .pack import build_demo_pack, build_druiid_midi_pack, validate_pack, validate_zip
from .recipe import ROOTS, SCALES, MidiEssentialsRecipe


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
    if path.suffix.lower() == ".zip":
        return {"type": "zip", "result": validate_zip(path)}
    raise ValueError(f"unsupported path: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abletools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser("demo", help="build a deterministic demo pack")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--seed", type=int, default=1842)
    druiid = subparsers.add_parser("druiid-midi", help="build a deterministic DRUIID MIDI Essentials pack")
    druiid.add_argument("--output", type=Path, required=True)
    druiid.add_argument("--seed", type=int, default=1842)
    druiid.add_argument("--root", choices=ROOTS, default="A")
    druiid.add_argument("--scale", choices=tuple(SCALES), default="minor")
    druiid.add_argument("--bpm", type=int, default=120)
    druiid.add_argument("--bars", type=int, default=8)
    druiid.add_argument("--progression", type=int, nargs="+", default=[1, 6, 4, 5])
    druiid.add_argument("--upper-mutation", type=float, default=0.5)
    druiid.add_argument("--bass-mutation", type=float, default=0.5)
    druiid.add_argument("--motif-mutation", type=float, default=0.5)
    druiid.add_argument("--rhythm-mutation", type=float, default=0.5)
    druiid.add_argument("--humanize-ticks", type=int, default=4)
    validate = subparsers.add_parser("validate", help="validate an R1 file or pack")
    validate.add_argument("path", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "demo":
        output = build_demo_pack(args.output, args.seed)
        print(json.dumps({"status": "ok", "pack": str(output), "archive": str(output.with_suffix('.zip'))}))
        return 0
    if args.command == "druiid-midi":
        recipe = MidiEssentialsRecipe(
            seed=args.seed,
            root=args.root,
            scale=args.scale,
            bpm=args.bpm,
            bars=args.bars,
            progression=tuple(args.progression),
            upper_mutation=args.upper_mutation,
            bass_mutation=args.bass_mutation,
            motif_mutation=args.motif_mutation,
            rhythm_mutation=args.rhythm_mutation,
            humanize_ticks=args.humanize_ticks,
        )
        output = build_druiid_midi_pack(args.output, recipe)
        print(json.dumps({"status": "ok", "pack": str(output), "archive": str(output.with_suffix('.zip'))}))
        return 0
    result = _validate(args.path)
    print(json.dumps({"status": "ok", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
