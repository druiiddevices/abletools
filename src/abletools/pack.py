"""Validated pack builders plus deterministic ZIP creation and validation."""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from . import __version__
from .audio import validate_wav, write_kick_wav
from .capabilities import require_capability
from .druiid import GM_DRUM_MAPPING, GeneratedMidiAsset, generate_midi_essentials
from .hazy import GeneratedHazyMidiAsset, generate_hazy_midi_essentials
from .manifest import load_manifest, validate_manifest_data, validate_relative_path, write_manifest
from .midi import PPQ, validate_midi, write_chord_midi, write_midi_clip
from .recipe import HAZY_MODES, HazyMidiRecipe, MidiEssentialsRecipe
from .rack_blueprint import RACK_FAMILIES
from .rack_validation import validate_rack_blueprint_file

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _key_token(recipe: MidiEssentialsRecipe) -> str:
    root = recipe.root.replace("#", "s")
    quality = "maj" if recipe.scale == "major" else "min"
    return f"{root}{quality}"


def _asset_filename(recipe: MidiEssentialsRecipe, asset: GeneratedMidiAsset) -> str:
    relationship = {"A": "FOUNDATION", "B": "MUTATION_B", "C": "MUTATION_C"}[asset.variation]
    return (
        f"DRUIID_{asset.descriptor}_{relationship}_{recipe.bpm}_{_key_token(recipe)}_"
        f"S{recipe.seed:04d}_V01.mid"
    )


def _hazy_key_token(recipe: HazyMidiRecipe) -> str:
    return f"{recipe.root.replace('#', 's')}_{recipe.mode}"


def _hazy_asset_filename(recipe: HazyMidiRecipe, asset: GeneratedHazyMidiAsset) -> str:
    relationship = {"A": "FOUNDATION", "B": "RELATED_B", "C": "RELATED_C"}[asset.variation]
    return (
        f"HAZY_{asset.descriptor}_{relationship}_{recipe.bpm}_{_hazy_key_token(recipe)}_"
        f"S{recipe.seed:04d}_V01.mid"
    )


def _validate_midi_entry(path: Path, item: dict[str, Any]) -> dict[str, Any]:
    metadata = item["metadata"]
    for field in ("bars", "tempo_bpm"):
        if field not in metadata:
            raise ValueError(f"MIDI file metadata requires {field}: {item['path']}")
    format_metadata = item["format"]
    if format_metadata.get("container") != "Standard MIDI File":
        raise ValueError("MIDI file format metadata must declare Standard MIDI File")
    expected_midi_format = format_metadata.get("midi_format")
    expected_ppq = format_metadata.get("ppq")
    if expected_midi_format is None or expected_ppq is None:
        raise ValueError("MIDI file format metadata requires midi_format and ppq")
    note_range_data = metadata.get("note_range")
    if note_range_data is not None and (
        not isinstance(note_range_data, list) or len(note_range_data) != 2
    ):
        raise ValueError(f"MIDI note_range metadata must contain two values: {item['path']}")
    note_range = tuple(note_range_data) if note_range_data is not None else None
    drum_mapping = metadata.get("drum_mapping")
    if drum_mapping is not None and not isinstance(drum_mapping, dict):
        raise ValueError(f"MIDI drum_mapping metadata must be an object: {item['path']}")
    channel = metadata.get("channel")
    if channel is not None and (
        isinstance(channel, bool) or not isinstance(channel, int) or not 1 <= channel <= 16
    ):
        raise ValueError(f"MIDI channel metadata must be from 1 to 16: {item['path']}")
    expected_channel = channel - 1 if channel is not None else None
    return validate_midi(
        path,
        expected_midi_format=expected_midi_format,
        expected_ppq=expected_ppq,
        expected_bars=metadata["bars"],
        expected_bpm=metadata["tempo_bpm"],
        note_range=note_range,
        drum_mapping=drum_mapping,
        expected_channel=expected_channel,
    )


def _validate_midi_metadata_consistency(
    manifest: dict[str, Any], item: dict[str, Any], result: dict[str, Any]
) -> None:
    """Require declarations at every layer to describe the parsed MIDI bytes."""
    metadata = item["metadata"]
    for field in ("seed", "tempo_bpm", "bars", "meter", "key", "root", "scale", "profile_version"):
        if field not in manifest:
            continue
        if field not in metadata:
            raise ValueError(f"MIDI metadata missing top-level field: {field}")
        if metadata[field] != manifest[field]:
            raise ValueError(f"MIDI metadata mismatch for {field}: {item['path']}")

    format_metadata = item["format"]
    if manifest.get("style") in {"DRUIID", "HAZY"} and manifest.get("asset_type") == "midi_essentials":
        if format_metadata.get("midi_format") != 0 or format_metadata.get("ppq") != PPQ:
            raise ValueError(f"{manifest['style']} MIDI Essentials requires MIDI format 0 at 480 PPQ")
        if manifest["format"].get("midi_format") != 0 or manifest["format"].get("ppq") != PPQ:
            raise ValueError(
                f"{manifest['style']} MIDI Essentials top-level format must be format 0 at 480 PPQ"
            )
    if result["format"] != format_metadata["midi_format"]:
        raise ValueError(f"MIDI format metadata disagrees with parsed result: {item['path']}")
    if result["ppq"] != format_metadata["ppq"]:
        raise ValueError(f"MIDI PPQ metadata disagrees with parsed result: {item['path']}")

    if item["role"] == "chords":
        degree_sequence = metadata.get("degree_sequence")
        chord_symbols = metadata.get("chord_symbols")
        if (
            not isinstance(degree_sequence, list)
            or not degree_sequence
            or any(
                isinstance(degree, bool) or not isinstance(degree, int) or not 1 <= degree <= 7
                for degree in degree_sequence
            )
        ):
            raise ValueError(f"chord metadata requires a valid degree sequence: {item['path']}")
        if (
            not isinstance(chord_symbols, list)
            or not chord_symbols
            or any(not isinstance(symbol, str) or not symbol.strip() for symbol in chord_symbols)
        ):
            raise ValueError(f"chord metadata requires non-empty chord symbols: {item['path']}")
        if len(degree_sequence) != len(chord_symbols):
            raise ValueError(f"chord degree sequence and symbols must have matching lengths: {item['path']}")

    if item["role"] == "drum_pattern":
        drum_mapping = metadata.get("drum_mapping")
        channel = metadata.get("channel")
        if drum_mapping != GM_DRUM_MAPPING:
            raise ValueError(f"drum mapping must match the declared General MIDI mapping: {item['path']}")
        if channel != 10:
            raise ValueError(f"drum channel must be MIDI channel 10: {item['path']}")
        if result["used_channels"] != [channel]:
            raise ValueError(f"drum channel metadata disagrees with parsed MIDI: {item['path']}")
        if not set(result["used_notes"]) <= set(drum_mapping.values()):
            raise ValueError(f"drum mapping metadata disagrees with parsed MIDI: {item['path']}")

    if manifest.get("style") == "HAZY" and manifest.get("asset_type") == "midi_essentials":
        _validate_hazy_midi_metadata(manifest, item, result)


def _validate_hazy_midi_metadata(
    manifest: dict[str, Any], item: dict[str, Any], result: dict[str, Any]
) -> None:
    """Check HAZY creative declarations against the actual notes and pack identity."""
    metadata = item["metadata"]
    required = {
        "borrowed_tones",
        "chord_symbols",
        "degree_sequence",
        "harmonic_archetype",
        "mode",
        "timing_model",
        "variation",
        "variation_relationship",
        "voicing_or_color_behavior",
    }
    missing = sorted(required - metadata.keys())
    if missing:
        raise ValueError(f"HAZY MIDI metadata missing required fields: {', '.join(missing)}")
    if metadata["mode"] != manifest["scale"]:
        raise ValueError(f"HAZY mode metadata disagrees with pack scale: {item['path']}")
    recipe = manifest.get("recipe", {})
    if metadata["mode"] != recipe.get("mode"):
        raise ValueError(f"HAZY mode metadata disagrees with the canonical recipe: {item['path']}")
    if metadata["harmonic_archetype"] != recipe.get("harmonic_archetype"):
        raise ValueError(f"HAZY harmonic archetype disagrees with the canonical recipe: {item['path']}")
    degree_sequence = metadata["degree_sequence"]
    chord_symbols = metadata["chord_symbols"]
    if (
        not isinstance(degree_sequence, list)
        or not degree_sequence
        or any(
            isinstance(degree, bool) or not isinstance(degree, int) or not 1 <= degree <= 7
            for degree in degree_sequence
        )
        or degree_sequence != recipe.get("progression")
    ):
        raise ValueError(f"HAZY degree sequence disagrees with the canonical recipe: {item['path']}")
    if (
        not isinstance(chord_symbols, list)
        or len(chord_symbols) != len(degree_sequence)
        or any(not isinstance(symbol, str) or not symbol.strip() for symbol in chord_symbols)
    ):
        raise ValueError(f"HAZY chord-symbol metadata is incomplete: {item['path']}")
    if metadata["variation"] not in {"A", "B", "C"}:
        raise ValueError(f"HAZY variation must be A, B, or C: {item['path']}")
    for field in ("timing_model", "variation_relationship", "voicing_or_color_behavior"):
        if not metadata[field] or not isinstance(metadata[field], (str, dict)):
            raise ValueError(f"HAZY MIDI metadata requires non-empty {field}: {item['path']}")

    borrowed_tones = metadata["borrowed_tones"]
    if not isinstance(borrowed_tones, list):
        raise ValueError(f"HAZY borrowed_tones metadata must be a list: {item['path']}")
    if item["role"] == "drum_pattern":
        if borrowed_tones:
            raise ValueError(f"HAZY drum clips cannot declare harmonic borrowed tones: {item['path']}")
        return

    try:
        intervals = HAZY_MODES[manifest["scale"]]
    except KeyError as error:
        raise ValueError(f"unsupported HAZY mode in manifest: {manifest['scale']}") from error
    note_names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    root_pc = note_names.index(manifest["root"])
    allowed_pitch_classes = {(root_pc + interval) % 12 for interval in intervals}
    actual_borrowed = {
        pitch for pitch in result["used_notes"] if pitch % 12 not in allowed_pitch_classes
    }
    declared_borrowed: set[int] = set()
    for declaration in borrowed_tones:
        if not isinstance(declaration, dict):
            raise ValueError(f"HAZY borrowed tone declarations must be objects: {item['path']}")
        midi_note = declaration.get("midi_note")
        pitch_class = declaration.get("pitch_class")
        reason = declaration.get("reason")
        if (
            isinstance(midi_note, bool)
            or not isinstance(midi_note, int)
            or not 0 <= midi_note <= 127
            or pitch_class != note_names[midi_note % 12]
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise ValueError(f"malformed HAZY borrowed tone declaration: {item['path']}")
        if midi_note in declared_borrowed:
            raise ValueError(f"duplicate HAZY borrowed tone declaration: {item['path']}")
        declared_borrowed.add(midi_note)
    if declared_borrowed != actual_borrowed:
        raise ValueError(f"HAZY borrowed notes must be declared exactly: {item['path']}")

    if item["role"] == "chords":
        voicings = metadata.get("voicings")
        colors = metadata.get("color_behavior")
        pedal = metadata.get("pedal")
        voice_leading = metadata.get("voice_leading")
        if (
            not isinstance(voicings, list)
            or len(voicings) != len(metadata["degree_sequence"])
            or any(
                not isinstance(voicing, list)
                or len(voicing) < 2
                or any(
                    isinstance(note, bool) or not isinstance(note, int) or not 0 <= note <= 127
                    for note in voicing
                )
                for voicing in voicings
            )
        ):
            raise ValueError(f"HAZY chord voicing metadata is incomplete: {item['path']}")
        if (
            not isinstance(colors, list)
            or len(colors) != len(voicings)
            or any(not isinstance(color, str) or not color for color in colors)
        ):
            raise ValueError(f"HAZY chord color metadata is incomplete: {item['path']}")
        if not isinstance(pedal, dict) or not isinstance(voice_leading, dict):
            raise ValueError(f"HAZY chord pedal and voice-leading metadata are required: {item['path']}")
        declared_harmonic_notes = {pitch for voicing in voicings for pitch in voicing}
        if declared_harmonic_notes | declared_borrowed != set(result["used_notes"]):
            raise ValueError(f"HAZY chord voicings disagree with parsed MIDI notes: {item['path']}")
        transition_movements: list[int] = []
        exact_common: list[int] = []
        pitch_class_common: list[int] = []
        for previous, current in zip(voicings, voicings[1:]):
            transition_movements.append(
                sum(min(abs(note - prior) for prior in previous) for note in current)
            )
            exact_common.append(len(set(previous) & set(current)))
            pitch_class_common.append(
                len({note % 12 for note in previous} & {note % 12 for note in current})
            )
        expected_voice_leading = {
            "exact_common_tone_counts": exact_common,
            "max_transition_movement": max(transition_movements, default=0),
            "pitch_class_common_tone_counts": pitch_class_common,
            "total_transition_movement": sum(transition_movements),
            "transition_movements": transition_movements,
        }
        if voice_leading != expected_voice_leading:
            raise ValueError(f"HAZY voice-leading metadata is inaccurate: {item['path']}")
        pedal_indices = pedal.get("chord_indices")
        pedal_note = pedal.get("midi_note")
        if not isinstance(pedal_indices, list) or any(
            isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(voicings)
            for index in pedal_indices
        ):
            raise ValueError(f"HAZY pedal metadata is malformed: {item['path']}")
        if pedal_indices and any(pedal_note not in voicings[index] for index in pedal_indices):
            raise ValueError(f"HAZY pedal metadata disagrees with chord voicings: {item['path']}")


def _validate_hazy_inventory(manifest: dict[str, Any]) -> None:
    if manifest.get("style") != "HAZY" or manifest.get("asset_type") != "midi_essentials":
        return
    expected = {
        (role, variation)
        for role in ("chords", "bass", "motif", "arpeggio", "drum_pattern")
        for variation in ("A", "B", "C")
    }
    identities = [
        (item["role"], item["metadata"].get("variation")) for item in manifest["files"]
    ]
    if len(identities) != 15 or len(set(identities)) != 15 or set(identities) != expected:
        raise ValueError("HAZY MIDI Essentials requires exactly five roles in related A/B/C forms")
    if any(
        not item["path"].startswith("MIDI/HAZY_")
        or PurePosixPath(item["path"]).suffix.lower() not in {".mid", ".midi"}
        for item in manifest["files"]
    ):
        raise ValueError("HAZY MIDI Essentials files require canonical HAZY MIDI names")


def _readme_for_midi_pack(pack_name: str, recipe: MidiEssentialsRecipe) -> str:
    return (
        f"# {pack_name}\n\n"
        "A deterministic DRUIID MIDI Essentials pack generated by Abletools. "
        "DRUIID is a provisional musical-behavior profile; no timbral identity is claimed.\n\n"
        f"- Key: {recipe.key}\n"
        f"- Tempo: {recipe.bpm} BPM\n"
        "- Meter: 4/4\n"
        f"- Length: {recipe.bars} bars per clip\n"
        f"- Seed: {recipe.seed}\n"
        f"- Profile: {recipe.profile_version}\n\n"
        "Import the MIDI files from `MIDI/` into Ableton Live. A is the foundation, "
        "B is a restrained mutation, and C is a stronger bounded mutation. "
        "The drum clips use the declared General MIDI mapping on channel 10.\n"
    )


def _readme_for_hazy_pack(
    pack_name: str,
    recipe: HazyMidiRecipe,
    assets: list[GeneratedHazyMidiAsset],
) -> str:
    lines = [
        f"# {pack_name}",
        "",
        "A deterministic pack of original HAZY MIDI material generated by Abletools. "
        "HAZY describes a broad hazy-analog aesthetic; this pack does not recreate identifiable artist material.",
        "",
        f"- Key/mode: {recipe.key}",
        f"- Harmonic archetype: {recipe.harmonic_archetype}",
        f"- Degree sequence: {', '.join(str(degree) for degree in recipe.progression)}",
        f"- Tempo: {recipe.bpm} BPM",
        "- Meter and MIDI format: 4/4, type 0, 480 PPQ",
        f"- Length: {recipe.bars} bars per clip",
        f"- Seed: {recipe.seed}",
        f"- Profile: {recipe.profile_version}",
        "",
        "A is the foundation. B preserves its identity with a restrained role-specific change. "
        "C applies a stronger bounded change and declares every chromatic tone.",
        "Drums use the declared General MIDI mapping on channel 10.",
        "",
        "## Clip inventory",
        "",
    ]
    for asset in assets:
        metadata = asset.metadata
        borrowed = metadata["borrowed_tones"]
        borrowed_text = (
            ", ".join(
                f"{entry['pitch_class']} ({entry['midi_note']}: {entry['reason']})"
                for entry in borrowed
            )
            if borrowed
            else "none"
        )
        timing = metadata["timing_model"]
        timing_text = json.dumps(timing, sort_keys=True, separators=(",", ":")) if isinstance(timing, dict) else timing
        lines.extend(
            (
                f"### {_hazy_asset_filename(recipe, asset)}",
                "",
                f"- Role / variation: {asset.role} / {asset.variation}",
                f"- Scale or mode: {recipe.mode}",
                f"- Degree sequence: {', '.join(str(degree) for degree in metadata['degree_sequence'])}",
                f"- Chord symbols: {', '.join(metadata['chord_symbols'])}",
                f"- Voicing or color: {metadata['voicing_or_color_behavior']}",
                f"- Borrowed tones: {borrowed_text}",
                f"- Timing model: {timing_text}",
                f"- Variation relationship: {metadata['variation_relationship']}",
                "",
            )
        )
    return "\n".join(lines)


def _write_readme(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8", newline="\n")
    return path


def build_druiid_midi_pack(output: str | Path, recipe: MidiEssentialsRecipe) -> Path:
    """Build, validate, and archive one DRUIID MIDI Essentials pack."""
    require_capability("druiid_midi_essentials")
    require_capability("standard_midi")
    require_capability("zip_pack")
    if recipe.style != "DRUIID":
        raise ValueError("DRUIID MIDI Essentials requires the DRUIID profile")

    root = Path(output)
    midi_dir = root / "MIDI"
    midi_dir.mkdir(parents=True, exist_ok=True)
    pack_name = f"DRUIID_MIDI_ESSENTIALS_{_key_token(recipe)}_S{recipe.seed:04d}"
    _write_readme(root / "README.md", _readme_for_midi_pack(pack_name, recipe))

    files: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    for asset in generate_midi_essentials(recipe):
        path = write_midi_clip(
            midi_dir / _asset_filename(recipe, asset),
            asset.notes,
            bpm=recipe.bpm,
            bars=recipe.bars,
            track_name=f"DRUIID {asset.role} {asset.variation}",
        )
        relative = path.relative_to(root).as_posix()
        item = {
            "path": relative,
            "role": asset.role,
            "sha256": _sha256(path),
            "format": {"container": "Standard MIDI File", "midi_format": 0, "ppq": PPQ},
            "metadata": asset.metadata,
        }
        result = _validate_midi_entry(path, item)
        files.append(item)
        validations.append({"file": relative, "validator": "abletools.midi", "result": result})

    manifest = {
        "schema_version": "1.0.0",
        "pack_name": pack_name,
        "version": "1.0.0",
        "generator_version": __version__,
        "style": "DRUIID",
        "asset_type": "midi_essentials",
        "seed": recipe.seed,
        "tempo_bpm": recipe.bpm,
        "meter": "4/4",
        "key": recipe.key,
        "root": recipe.root,
        "scale": recipe.scale,
        "bars": recipe.bars,
        "profile_version": recipe.profile_version,
        "recipe": recipe.canonical_data(),
        "files": files,
        "format": {"container": "Standard MIDI File", "midi_format": 0, "ppq": PPQ},
        "generation_notes": [
            "Degree-first, scale-aware DRUIID musical behavior with bounded A/B/C mutation.",
            "No non-deterministic generation stage and no claimed DRUIID timbral profile.",
        ],
        "validation": validations,
        "dependencies": [],
    }
    write_manifest(root / "manifest.json", manifest)
    validate_pack(root)
    archive = write_deterministic_zip(root, root.with_suffix(".zip"))
    validate_zip(archive)
    return root


def build_hazy_midi_pack(output: str | Path, recipe: HazyMidiRecipe) -> Path:
    """Build, validate, and archive one original HAZY MIDI Essentials pack."""
    require_capability("hazy_midi_essentials")
    require_capability("standard_midi")
    require_capability("zip_pack")
    if recipe.style != "HAZY":
        raise ValueError("HAZY MIDI Essentials requires the HAZY profile")

    root = Path(output)
    midi_dir = root / "MIDI"
    midi_dir.mkdir(parents=True, exist_ok=True)
    assets = generate_hazy_midi_essentials(recipe)
    pack_name = f"HAZY_MIDI_ESSENTIALS_{_hazy_key_token(recipe)}_S{recipe.seed:04d}"
    _write_readme(root / "README.md", _readme_for_hazy_pack(pack_name, recipe, assets))

    files: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    for asset in assets:
        path = write_midi_clip(
            midi_dir / _hazy_asset_filename(recipe, asset),
            asset.notes,
            bpm=recipe.bpm,
            bars=recipe.bars,
            track_name=f"HAZY {asset.role} {asset.variation}",
        )
        relative = path.relative_to(root).as_posix()
        item = {
            "path": relative,
            "role": asset.role,
            "sha256": _sha256(path),
            "format": {"container": "Standard MIDI File", "midi_format": 0, "ppq": PPQ},
            "metadata": asset.metadata,
        }
        result = _validate_midi_entry(path, item)
        files.append(item)
        validations.append({"file": relative, "validator": "abletools.midi", "result": result})

    manifest = {
        "schema_version": "1.0.0",
        "pack_name": pack_name,
        "version": "1.0.0",
        "generator_version": __version__,
        "style": "HAZY",
        "asset_type": "midi_essentials",
        "seed": recipe.seed,
        "tempo_bpm": recipe.bpm,
        "meter": "4/4",
        "key": recipe.key,
        "root": recipe.root,
        "scale": recipe.scale,
        "bars": recipe.bars,
        "profile_version": recipe.profile_version,
        "recipe": recipe.canonical_data(),
        "files": files,
        "format": {"container": "Standard MIDI File", "midi_format": 0, "ppq": PPQ},
        "generation_notes": [
            "Original HAZY modal behavior with role-isolated deterministic streams and related A/B/C forms.",
            "Chromatic notes are sparse, declared per asset, and checked against the parsed MIDI bytes.",
            "No native Ableton, Serum 2, Max for Live, WAV, or publication stage is present.",
        ],
        "validation": validations,
        "dependencies": [],
    }
    write_manifest(root / "manifest.json", manifest)
    validate_pack(root)
    archive = write_deterministic_zip(root, root.with_suffix(".zip"))
    validate_zip(archive)
    return root


def build_demo_pack(output: str | Path, seed: int) -> Path:
    """Build the backwards-compatible MIDI/WAV smoke pack under the strict contract."""
    require_capability("standard_midi")
    require_capability("pcm_wav")
    require_capability("zip_pack")
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
    midi_metadata = {
        "bars": 8,
        "chord_symbols": ["Am(add9)", "Fmaj7", "Dm7", "G(add9)"],
        "degree_sequence": [1, 6, 4, 7],
        "key": "A minor",
        "meter": "4/4",
        "non_deterministic_stage": None,
        "profile_version": "DRUIID_R1",
        "role": "chords",
        "root": "A",
        "scale": "minor",
        "seed": seed,
        "tempo_bpm": 120,
    }
    wav_metadata = {
        "channels": 1,
        "duration_seconds": 0.8,
        "non_deterministic_stage": None,
        "role": "kick_one_shot",
        "sample_rate": 48_000,
        "sample_width_bits": 24,
        "seed": seed,
    }
    midi_result = validate_midi(
        midi_path,
        expected_midi_format=0,
        expected_ppq=PPQ,
        expected_bars=8,
        expected_bpm=120,
    )
    wav_result = validate_wav(wav_path)
    files = [
        {
            "path": midi_path.relative_to(root).as_posix(),
            "role": "chords",
            "sha256": _sha256(midi_path),
            "format": {"container": "Standard MIDI File", "midi_format": 0, "ppq": PPQ},
            "metadata": midi_metadata,
        },
        {
            "path": wav_path.relative_to(root).as_posix(),
            "role": "kick_one_shot",
            "sha256": _sha256(wav_path),
            "format": {"channels": 1, "codec": "PCM", "sample_rate": 48_000, "sample_width_bits": 24},
            "metadata": wav_metadata,
        },
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
        "root": "A",
        "scale": "minor",
        "bars": 8,
        "profile_version": "DRUIID_R1",
        "recipe": {"demo": True, "seed": seed},
        "files": files,
        "format": {"midi": files[0]["format"], "wav": files[1]["format"]},
        "generation_notes": ["Deterministic standard-library reference render."],
        "validation": [
            {"file": files[0]["path"], "validator": "abletools.midi", "result": midi_result},
            {"file": files[1]["path"], "validator": "abletools.audio", "result": wav_result},
        ],
        "dependencies": [],
    }
    _write_readme(
        root / "README.md",
        f"# {manifest['pack_name']}\n\nDeterministic Abletools smoke pack with one MIDI clip and one WAV.\n",
    )
    write_manifest(root / "manifest.json", manifest)
    validate_pack(root)
    archive = write_deterministic_zip(root, root.with_suffix(".zip"))
    validate_zip(archive)
    return root


def validate_pack(root: str | Path) -> dict[str, Any]:
    """Validate a directory pack, its complete inventory, and recorded results."""
    pack_root = Path(root)
    readme = pack_root / "README.md"
    if not readme.is_file() or not readme.read_text(encoding="utf-8").strip():
        raise ValueError("pack requires a non-empty README.md")
    manifest = load_manifest(pack_root / "manifest.json", check_files=True)
    _validate_hazy_inventory(manifest)
    if manifest.get("asset_type") == "ableton_rack_blueprints":
        if len(manifest["files"]) != len(RACK_FAMILIES):
            raise ValueError("rack blueprint pack requires exactly five files")
        families = [item["metadata"].get("family") for item in manifest["files"]]
        if tuple(families) != RACK_FAMILIES:
            raise ValueError("rack blueprint pack must contain the canonical family inventory in order")
        for item in manifest["files"]:
            if not item["path"].startswith("RACKS/BLUEPRINTS/"):
                raise ValueError("rack blueprints must be stored under RACKS/BLUEPRINTS")
    expected_files = {"README.md", "manifest.json", *(item["path"] for item in manifest["files"])}
    actual_files = {
        path.relative_to(pack_root).as_posix()
        for path in pack_root.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        extra = sorted(actual_files - expected_files)
        missing = sorted(expected_files - actual_files)
        raise ValueError(f"pack inventory mismatch; extra={extra}, missing={missing}")

    recorded = {item["file"]: item for item in manifest["validation"]}
    results: dict[str, Any] = {}
    for item in manifest["files"]:
        path = pack_root.joinpath(*PurePosixPath(item["path"]).parts)
        suffix = path.suffix.lower()
        if suffix in {".mid", ".midi"}:
            validator = "abletools.midi"
            result = _validate_midi_entry(path, item)
            _validate_midi_metadata_consistency(manifest, item, result)
        elif suffix == ".wav":
            validator = "abletools.audio"
            result = validate_wav(path)
            if result["sample_rate"] != 48_000 or result["sample_width_bits"] != 24:
                raise ValueError("R1 pack WAV files must be 48 kHz, 24-bit PCM")
        elif suffix == ".json" and manifest.get("asset_type") == "ableton_rack_blueprints":
            validator = "abletools.rack_blueprint"
            if item["format"] != {
                "container": "Abletools Rack Blueprint JSON",
                "media_type": "application/json",
                "schema_version": "1.0.0",
            }:
                raise ValueError(f"rack blueprint format metadata is invalid: {item['path']}")
            result = validate_rack_blueprint_file(path)
            metadata = item["metadata"]
            for field in ("seed", "style"):
                if metadata.get(field) != manifest.get(field):
                    raise ValueError(f"rack blueprint metadata mismatch for {field}: {item['path']}")
            if metadata.get("role") != "rack_blueprint" or item["role"] != "rack_blueprint":
                raise ValueError(f"rack blueprint role metadata is invalid: {item['path']}")
            if metadata.get("native_format") is not False:
                raise ValueError(f"rack blueprint must declare native_format false: {item['path']}")
            expected_metadata = {
                "device_count": result["devices"],
                "family": result["family"],
                "macro_count": result["macros"],
                "minimum_live_version": "12.0",
                "native_format": False,
                "rack_type": result["rack_type"],
                "role": "rack_blueprint",
                "seed": result["seed"],
                "style": result["style"],
            }
            if metadata != expected_metadata:
                raise ValueError(f"rack blueprint metadata disagrees with validated JSON: {item['path']}")
        else:
            raise ValueError(f"unsupported enabled asset type: {item['path']}")
        if recorded[item["path"]]["validator"] != validator:
            raise ValueError(f"validation-record validator mismatch: {item['path']}")
        if recorded[item["path"]]["result"] != result:
            raise ValueError(f"stale validation record: {item['path']}")
        results[item["path"]] = result
    return results


def write_deterministic_zip(root: str | Path, archive: str | Path) -> Path:
    """Write a byte-reproducible ZIP after validating the source pack."""
    require_capability("zip_pack")
    pack_root = Path(root)
    manifest = load_manifest(pack_root / "manifest.json", check_files=True)
    validate_pack(pack_root)
    entries = [pack_root / "README.md", pack_root / "manifest.json"] + [
        pack_root.joinpath(*PurePosixPath(item["path"]).parts) for item in manifest["files"]
    ]
    output = Path(archive)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as bundle:
        for path in sorted(entries, key=lambda item: item.relative_to(pack_root).as_posix()):
            relative = path.relative_to(pack_root).as_posix()
            info = zipfile.ZipInfo(f"{manifest['pack_name']}/{relative}", date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.flag_bits = 0x800
            bundle.writestr(info, path.read_bytes())
    return output


def validate_zip(path: str | Path) -> dict[str, Any]:
    """Validate ZIP path safety, exact inventory, checksums, and extracted assets."""
    require_capability("zip_pack")
    archive = Path(path)
    with zipfile.ZipFile(archive, "r") as bundle:
        infos = bundle.infolist()
        names = [info.filename for info in infos]
        if not names or len(names) != len({name.casefold() for name in names}):
            raise ValueError("ZIP must contain a unique, non-empty file inventory")
        for info in infos:
            validate_relative_path(info.filename)
            if info.is_dir():
                raise ValueError("ZIP directory entries are not part of the canonical pack")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError("ZIP symbolic links are not allowed")
            if info.flag_bits & 0x1:
                raise ValueError("encrypted ZIP members are not allowed")
        top_levels = {PurePosixPath(name).parts[0] for name in names}
        if len(top_levels) != 1:
            raise ValueError("ZIP must contain exactly one top-level pack directory")
        prefix = next(iter(top_levels))
        manifest_name = f"{prefix}/manifest.json"
        readme_name = f"{prefix}/README.md"
        if manifest_name not in names or readme_name not in names:
            raise ValueError("ZIP requires manifest.json and README.md")
        try:
            manifest = json.loads(bundle.read(manifest_name).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as error:
            raise ValueError("ZIP contains an unreadable manifest") from error
        validate_manifest_data(manifest)
        if prefix != manifest["pack_name"]:
            raise ValueError("ZIP top-level directory must match manifest pack_name")
        expected = {manifest_name, readme_name} | {
            f"{prefix}/{item['path']}" for item in manifest["files"]
        }
        if set(names) != expected:
            raise ValueError("ZIP inventory does not match its manifest")
        try:
            readme = bundle.read(readme_name).decode("utf-8")
        except (UnicodeDecodeError, zipfile.BadZipFile) as error:
            raise ValueError("ZIP README.md must be non-empty UTF-8 text") from error
        if not readme.strip():
            raise ValueError("ZIP README.md must be non-empty UTF-8 text")
        for item in manifest["files"]:
            member = f"{prefix}/{item['path']}"
            if _sha256_bytes(bundle.read(member)) != item["sha256"]:
                raise ValueError(f"ZIP checksum mismatch: {item['path']}")

        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory) / prefix
            for name in names:
                destination = Path(directory).joinpath(*PurePosixPath(name).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(bundle.read(name))
            results = validate_pack(temporary_root)
    return {"files": len(manifest["files"]), "pack_name": manifest["pack_name"], "result": results}
