"""Build deterministic validated DRUIID and HAZY Drum One-Shot Essentials packs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .capabilities import require_capability
from .drum_audio import read_pcm24_mono, render_preview, validate_drum_wav, write_drum_voice, write_pcm24_mono
from .drum_recipe import (
    DRUM_FAMILIES,
    DRUM_FAMILY_SPECS,
    DrumEssentialsRecipe,
    DrumVoiceRecipe,
    drum_relative_path,
    preview_relative_path,
)
from .drum_validation import DRUM_ASSET_TYPE, DRUM_WAV_FORMAT
from .manifest import write_manifest
from .pack import _sha256, _write_readme, validate_pack, validate_zip, write_deterministic_zip


def _metadata(
    recipe: DrumEssentialsRecipe,
    *,
    role: str,
    family: str,
    variant: int,
    descriptor: str,
    result: dict[str, int | float | str],
) -> dict[str, Any]:
    return {
        "audio_shape_sha256": result["audio_shape_sha256"],
        "bit_depth": result["sample_width_bits"],
        "channels": result["channels"],
        "dc_offset": result["dc_offset"],
        "descriptor": descriptor,
        "duration_seconds": result["duration_seconds"],
        "family": family,
        "peak": result["peak"],
        "profile_version": recipe.profile_version,
        "rms": result["rms"],
        "role": role,
        "sample_rate": result["sample_rate"],
        "seed": recipe.seed,
        "style": recipe.style,
        "variant": variant,
    }


def _preview_placements(source_paths: dict[str, list[str]]) -> list[dict[str, Any]]:
    step = 12_000
    placements: list[dict[str, Any]] = []
    closed = source_paths["closed_hat"]
    for index in range(16):
        placements.append(
            {"gain": 0.24, "source": closed[index % len(closed)], "start_frame": index * step}
        )
    for step_index, variant in ((0, 0), (8, 1)):
        placements.append(
            {"gain": 0.62, "source": source_paths["kick"][variant], "start_frame": step_index * step}
        )
    for step_index, variant in ((4, 0), (12, 1)):
        placements.append(
            {"gain": 0.48, "source": source_paths["snare"][variant], "start_frame": step_index * step}
        )
    for step_index, variant in ((3, 0), (11, 1)):
        placements.append(
            {"gain": 0.22, "source": source_paths["shaker"][variant], "start_frame": step_index * step}
        )
    for step_index, variant in ((6, 0), (14, 3)):
        placements.append(
            {"gain": 0.30, "source": source_paths["percussion"][variant], "start_frame": step_index * step}
        )
    placements.append(
        {"gain": 0.22, "source": source_paths["open_hat"][0], "start_frame": 15 * step}
    )
    return sorted(placements, key=lambda item: (item["start_frame"], item["source"]))


def _readme(recipe: DrumEssentialsRecipe, files: list[dict[str, Any]]) -> str:
    lines = [
        f"# {recipe.style} Drum One-Shot Essentials",
        "",
        f"Forty original, deterministic mono drum one-shots in the {recipe.style} profile, plus one preview assembled only from included sounds.",
        "All source WAVs are 48 kHz, 24-bit PCM with strict level, DC, fade, duration, checksum, inventory, and packaging validation.",
        "",
        f"Profile intent: {recipe.profile.description}.",
        "No external samples or identifiable artist material were used. The preview is an audition aid and is not part of the 40-source count.",
        "Final subjective listening approval has not occurred.",
        "",
        "## Inventory",
        "",
    ]
    for family in DRUM_FAMILIES:
        lines.append(f"### {family.replace('_', ' ').title()}")
        lines.append("")
        for item in files:
            if item["role"] == "drum_one_shot" and item["metadata"]["family"] == family:
                lines.append(
                    f"- `{item['path']}` — {item['metadata']['duration_seconds']:.6f}s, "
                    f"peak {item['metadata']['peak']:.6f}, RMS {item['metadata']['rms']:.6f}."
                )
        lines.append("")
    preview = next(item for item in files if item["role"] == "preview")
    lines.extend(("### Preview", "", f"- `{preview['path']}` — source-only deterministic audition sequence.", ""))
    return "\n".join(lines)


def build_drum_essentials_pack(output: str | Path, recipe: DrumEssentialsRecipe) -> Path:
    """Build, strictly validate, and archive one exact 40-source drum catalog."""
    require_capability(f"{recipe.style.lower()}_drum_one_shot_essentials")
    require_capability("pcm_wav")
    require_capability("zip_pack")
    root = Path(output)
    files: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    source_paths: dict[str, list[str]] = {family: [] for family in DRUM_FAMILIES}
    decoded_sources: dict[str, list[float]] = {}

    for family in DRUM_FAMILIES:
        for variant in range(1, DRUM_FAMILY_SPECS[family].count + 1):
            voice = DrumVoiceRecipe(recipe, family, variant)
            relative = drum_relative_path(voice)
            path, render = write_drum_voice(root.joinpath(*relative.split("/")), voice)
            result = validate_drum_wav(path, family=family)
            metadata = _metadata(
                recipe,
                role="drum_one_shot",
                family=family,
                variant=variant,
                descriptor=voice.descriptor,
                result=result,
            )
            metadata["synthesis_parameters"] = render.synthesis_parameters
            item = {
                "path": relative,
                "role": "drum_one_shot",
                "sha256": _sha256(path),
                "format": DRUM_WAV_FORMAT,
                "metadata": metadata,
            }
            files.append(item)
            validations.append({"file": relative, "validator": "abletools.drum_audio", "result": result})
            source_paths[family].append(relative)
            decoded_sources[relative] = read_pcm24_mono(path)[0]

    placements = _preview_placements(source_paths)
    preview_relative = preview_relative_path(recipe)
    preview_path = write_pcm24_mono(
        root.joinpath(*preview_relative.split("/")),
        render_preview(decoded_sources, placements),
    )
    preview_result = validate_drum_wav(preview_path, family="preview")
    preview_metadata = _metadata(
        recipe,
        role="preview",
        family="preview",
        variant=1,
        descriptor="AUDITION",
        result=preview_result,
    )
    referenced = sorted({placement["source"] for placement in placements})
    preview_metadata["source_assembly"] = {
        "engine": "included-one-shot-mix-v1",
        "placements": placements,
        "source_sha256": {
            relative: next(item["sha256"] for item in files if item["path"] == relative)
            for relative in referenced
        },
    }
    files.append(
        {
            "path": preview_relative,
            "role": "preview",
            "sha256": _sha256(preview_path),
            "format": DRUM_WAV_FORMAT,
            "metadata": preview_metadata,
        }
    )
    validations.append(
        {"file": preview_relative, "validator": "abletools.drum_audio", "result": preview_result}
    )

    pack_name = f"{recipe.style}_DRUM_ONE_SHOT_ESSENTIALS_S{recipe.seed:04d}"
    manifest = {
        "schema_version": "1.0.0",
        "pack_name": pack_name,
        "version": "1.0.0",
        "generator_version": __version__,
        "style": recipe.style,
        "asset_type": DRUM_ASSET_TYPE,
        "seed": recipe.seed,
        "profile_version": recipe.profile_version,
        "recipe": recipe.canonical_data(),
        "files": files,
        "format": DRUM_WAV_FORMAT,
        "generation_notes": [
            "Original synthesis only; no source samples or native Ableton serialization.",
            "Family and voice RNG namespaces are isolated and deterministic.",
            "Strict format, signal, metadata, inventory, preview provenance, and ZIP validation completed.",
            "Subjective listening approval and release publication have not occurred.",
        ],
        "validation": validations,
        "dependencies": [],
    }
    _write_readme(root / "README.md", _readme(recipe, files))
    write_manifest(root / "manifest.json", manifest)
    validate_pack(root)
    archive = write_deterministic_zip(root, root.with_suffix(".zip"))
    validate_zip(archive)
    return root
