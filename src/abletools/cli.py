"""Abletools command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audio import validate_wav
from .drum_pack import build_drum_essentials_pack
from .drum_recipe import DrumEssentialsRecipe
from .manifest import load_manifest
from .midi import validate_midi
from .pack import build_demo_pack, build_druiid_midi_pack, build_hazy_midi_pack, validate_pack, validate_zip
from .recipe import HAZY_ARCHETYPES, HAZY_MODES, ROOTS, SCALES, HazyMidiRecipe, MidiEssentialsRecipe
from .rack_blueprint import RackBlueprintRecipe
from .rack_pack import build_rack_blueprint_pack
from .rack_validation import validate_rack_blueprint_file


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
    if path.suffix.lower() == ".json":
        return {"type": "rack_blueprint", "result": validate_rack_blueprint_file(path)}
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
    hazy = subparsers.add_parser("hazy-midi", help="build a deterministic HAZY MIDI Essentials pack")
    hazy.add_argument("--output", type=Path, required=True)
    hazy.add_argument("--seed", type=int, default=1842)
    hazy.add_argument("--root", choices=ROOTS, default="D")
    hazy.add_argument("--mode", choices=tuple(HAZY_MODES), default="dorian")
    hazy.add_argument("--bpm", type=int, default=92)
    hazy.add_argument("--bars", type=int, default=8)
    hazy.add_argument("--harmonic-archetype", choices=tuple(HAZY_ARCHETYPES), default="modal_pedal")
    hazy.add_argument("--progression", type=int, nargs="+")
    hazy.add_argument("--color-amount", type=float, default=0.65)
    hazy.add_argument("--ambiguity", type=float, default=0.6)
    hazy.add_argument("--tension", type=float, default=0.4)
    hazy.add_argument("--pedal-preference", type=float, default=0.7)
    hazy.add_argument("--common-tone-preference", type=float, default=0.75)
    hazy.add_argument("--groove-drift", type=int, default=6)
    hazy.add_argument("--chord-mutation", type=float, default=0.55)
    hazy.add_argument("--bass-mutation", type=float, default=0.45)
    hazy.add_argument("--motif-mutation", type=float, default=0.5)
    hazy.add_argument("--arpeggio-mutation", type=float, default=0.55)
    hazy.add_argument("--drum-mutation", type=float, default=0.5)
    racks = subparsers.add_parser(
        "rack-blueprints", help="build deterministic Ableton rack blueprint specifications"
    )
    racks.add_argument("--output", type=Path, required=True)
    racks.add_argument("--style", choices=("DRUIID", "HAZY"), required=True)
    racks.add_argument("--seed", type=int, default=1842)
    drums = subparsers.add_parser(
        "drum-essentials", help="build deterministic DRUIID or HAZY Drum One-Shot Essentials"
    )
    drums.add_argument("--output", type=Path, required=True)
    drums.add_argument("--style", choices=("DRUIID", "HAZY"), required=True)
    drums.add_argument("--seed", type=int, default=1842)
    drums.add_argument("--kick-character", type=float, default=0.5)
    drums.add_argument("--snare-character", type=float, default=0.5)
    drums.add_argument("--hat-character", type=float, default=0.5)
    drums.add_argument("--shaker-character", type=float, default=0.5)
    drums.add_argument("--percussion-character", type=float, default=0.5)
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
    if args.command == "hazy-midi":
        recipe = HazyMidiRecipe(
            seed=args.seed,
            root=args.root,
            mode=args.mode,
            bpm=args.bpm,
            bars=args.bars,
            harmonic_archetype=args.harmonic_archetype,
            progression=tuple(args.progression) if args.progression is not None else None,
            color_amount=args.color_amount,
            ambiguity=args.ambiguity,
            tension=args.tension,
            pedal_preference=args.pedal_preference,
            common_tone_preference=args.common_tone_preference,
            groove_drift=args.groove_drift,
            chord_mutation=args.chord_mutation,
            bass_mutation=args.bass_mutation,
            motif_mutation=args.motif_mutation,
            arpeggio_mutation=args.arpeggio_mutation,
            drum_mutation=args.drum_mutation,
        )
        output = build_hazy_midi_pack(args.output, recipe)
        print(json.dumps({"status": "ok", "pack": str(output), "archive": str(output.with_suffix('.zip'))}))
        return 0
    if args.command == "rack-blueprints":
        output = build_rack_blueprint_pack(
            args.output, RackBlueprintRecipe(seed=args.seed, style=args.style)
        )
        print(json.dumps({"status": "ok", "pack": str(output), "archive": str(output.with_suffix('.zip'))}))
        return 0
    if args.command == "drum-essentials":
        output = build_drum_essentials_pack(
            args.output,
            DrumEssentialsRecipe(
                seed=args.seed,
                style=args.style,
                kick_character=args.kick_character,
                snare_character=args.snare_character,
                hat_character=args.hat_character,
                shaker_character=args.shaker_character,
                percussion_character=args.percussion_character,
            ),
        )
        print(json.dumps({"status": "ok", "pack": str(output), "archive": str(output.with_suffix('.zip'))}))
        return 0
    result = _validate(args.path)
    print(json.dumps({"status": "ok", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
