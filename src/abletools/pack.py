"""Demo pack builder and directory validation."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from . import __version__
from .audio import validate_wav, write_kick_wav
from .manifest import load_manifest, write_manifest
from .midi import validate_midi, write_chord_midi


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def build_demo_pack(output: str | Path, seed: int) -> Path:
    root = Path(output)
    midi_dir = root / "MIDI"
    wav_dir = root / "WAV"
    midi_path = write_chord_midi(
        midi_dir / f"DRUIID_CHORDS_OPEN_120_Amin_S{seed:04d}_V01.mid",
        [[57, 60, 64, 71], [53, 57, 60, 64], [62, 65, 69, 72], [55, 59, 62, 69]],
        bpm=120,
        bars=8,
        seed=seed,
    )
    wav_path = write_kick_wav(
        wav_dir / f"DRUIID_KICK_COMPACT_S{seed:04d}_V01.wav",
        seed=seed,
    )
    midi_validation = validate_midi(midi_path)
    wav_validation = validate_wav(wav_path)
    files = [
        {"path": midi_path.relative_to(root).as_posix(), "role": "chord_midi", "sha256": _sha256(midi_path)},
        {"path": wav_path.relative_to(root).as_posix(), "role": "kick_one_shot", "sha256": _sha256(wav_path)},
    ]
    manifest = {
        "schema_version": "1.0.0",
        "pack_name": f"DRUIID_DEMO_S{seed:04d}",
        "version": "1.0.0",
        "generator_version": __version__,
        "style": "DRUIID",
        "asset_type": "mixed_demo_pack",
        "seed": seed,
        "tempo_bpm": 120,
        "meter": "4/4",
        "key": "A minor",
        "files": files,
        "generation_notes": ["Deterministic standard-library reference render."],
        "validation": [
            {"file": files[0]["path"], "validator": "abletools.midi", "result": midi_validation},
            {"file": files[1]["path"], "validator": "abletools.audio", "result": wav_validation},
        ],
        "dependencies": [],
    }
    manifest_path = write_manifest(root / "manifest.json", manifest)
    archive = root.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in (midi_path, wav_path, manifest_path):
            bundle.write(path, path.relative_to(root.parent))
    return root


def validate_pack(root: str | Path) -> dict[str, Any]:
    pack_root = Path(root)
    manifest = load_manifest(pack_root / "manifest.json", check_files=True)
    results: dict[str, Any] = {}
    for item in manifest["files"]:
        path = pack_root / item["path"]
        if item.get("sha256") != _sha256(path):
            raise ValueError(f"checksum mismatch: {item['path']}")
        suffix = path.suffix.lower()
        if suffix in {".mid", ".midi"}:
            results[item["path"]] = validate_midi(path)
        elif suffix == ".wav":
            results[item["path"]] = validate_wav(path)
        else:
            raise ValueError(f"unsupported R1 asset type: {item['path']}")
    return results
