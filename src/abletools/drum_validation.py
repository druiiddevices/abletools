"""Pack-level validation for deterministic Drum One-Shot Essentials."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from .drum_audio import (
    encode_pcm24_mono,
    read_pcm24_mono,
    render_preview,
    validate_drum_wav,
)
from .drum_recipe import (
    BIT_DEPTH,
    CHANNELS,
    DRUM_FAMILIES,
    DRUM_FAMILY_SPECS,
    DRUM_SOURCE_COUNT,
    SAMPLE_RATE,
    DrumEssentialsRecipe,
    DrumVoiceRecipe,
    drum_relative_path,
    preview_relative_path,
)

DRUM_ASSET_TYPE = "drum_one_shot_essentials"
DRUM_WAV_FORMAT = {
    "channels": CHANNELS,
    "codec": "PCM",
    "container": "RIFF/WAVE",
    "sample_rate": SAMPLE_RATE,
    "sample_width_bits": BIT_DEPTH,
}


def _path(root: Path, relative: str) -> Path:
    return root.joinpath(*PurePosixPath(relative).parts)


def validate_drum_pack_declarations(manifest: dict[str, Any], root: Path) -> None:
    """Validate catalog identity, metadata, uniqueness, and preview provenance."""
    if manifest.get("asset_type") != DRUM_ASSET_TYPE:
        return
    if manifest.get("format") != DRUM_WAV_FORMAT:
        raise ValueError("Drum Essentials top-level WAV format metadata is invalid")
    try:
        recipe = DrumEssentialsRecipe(**manifest.get("recipe", {}))
    except (TypeError, ValueError) as error:
        raise ValueError("Drum Essentials canonical recipe is invalid") from error
    if (
        manifest.get("style") != recipe.style
        or manifest.get("seed") != recipe.seed
        or manifest.get("profile_version") != recipe.profile_version
    ):
        raise ValueError("Drum Essentials top-level metadata disagrees with its recipe")

    sources = [item for item in manifest["files"] if item["role"] == "drum_one_shot"]
    previews = [item for item in manifest["files"] if item["role"] == "preview"]
    if len(sources) != DRUM_SOURCE_COUNT or len(previews) != 1 or len(manifest["files"]) != DRUM_SOURCE_COUNT + 1:
        raise ValueError("Drum Essentials requires exactly 40 source one-shots and one preview")
    expected_identities = {
        (family, variant)
        for family in DRUM_FAMILIES
        for variant in range(1, DRUM_FAMILY_SPECS[family].count + 1)
    }
    identities = [(item["metadata"].get("family"), item["metadata"].get("variant")) for item in sources]
    if len(set(identities)) != DRUM_SOURCE_COUNT or set(identities) != expected_identities:
        raise ValueError("Drum Essentials family inventory is incomplete or duplicated")
    expected_paths = [
        drum_relative_path(DrumVoiceRecipe(recipe, family, variant))
        for family in DRUM_FAMILIES
        for variant in range(1, DRUM_FAMILY_SPECS[family].count + 1)
    ]
    if [item["path"] for item in sources] != expected_paths:
        raise ValueError("Drum Essentials source inventory must use canonical names and order")
    if previews[0]["path"] != preview_relative_path(recipe):
        raise ValueError("Drum Essentials preview must use its canonical name")
    source_hashes = [item["sha256"] for item in sources]
    if len(set(source_hashes)) != DRUM_SOURCE_COUNT:
        raise ValueError("Drum Essentials contains duplicate source audio hashes")
    shape_hashes = [item["metadata"].get("audio_shape_sha256") for item in sources]
    if any(not isinstance(value, str) or len(value) != 64 for value in shape_hashes):
        raise ValueError("Drum Essentials source audio shape metadata is incomplete")
    if len(set(shape_hashes)) != DRUM_SOURCE_COUNT:
        raise ValueError("Drum Essentials contains gain-only duplicate source audio shapes")

    source_by_path = {item["path"]: item for item in sources}
    preview_metadata = previews[0]["metadata"]
    assembly = preview_metadata.get("source_assembly")
    if not isinstance(assembly, dict) or assembly.get("engine") != "included-one-shot-mix-v1":
        raise ValueError("Drum Essentials preview requires a supported source assembly")
    placements = assembly.get("placements")
    declared_hashes = assembly.get("source_sha256")
    if not isinstance(placements, list) or not placements or not isinstance(declared_hashes, dict):
        raise ValueError("Drum Essentials preview source assembly is incomplete")
    referenced = {placement.get("source") for placement in placements if isinstance(placement, dict)}
    if not referenced or not referenced <= source_by_path.keys():
        raise ValueError("Drum Essentials preview references material outside its pack")
    expected_hashes = {path: source_by_path[path]["sha256"] for path in sorted(referenced)}
    if declared_hashes != expected_hashes:
        raise ValueError("Drum Essentials preview source hashes are stale")
    decoded_sources = {path: read_pcm24_mono(_path(root, path))[0] for path in referenced}
    expected_preview = encode_pcm24_mono(render_preview(decoded_sources, placements))
    actual_preview = _path(root, previews[0]["path"]).read_bytes()
    if actual_preview != expected_preview:
        raise ValueError("Drum Essentials preview is not reconstructible from included one-shots")


def validate_drum_entry(
    root: Path,
    manifest: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, int | float | str]:
    """Validate one manifest WAV and require declarations to match parsed audio."""
    if item.get("format") != DRUM_WAV_FORMAT:
        raise ValueError(f"Drum Essentials WAV format metadata is invalid: {item['path']}")
    metadata = item["metadata"]
    for field, expected in (
        ("seed", manifest["seed"]),
        ("style", manifest["style"]),
        ("profile_version", manifest["profile_version"]),
        ("role", item["role"]),
        ("sample_rate", SAMPLE_RATE),
        ("bit_depth", BIT_DEPTH),
        ("channels", CHANNELS),
    ):
        if metadata.get(field) != expected:
            raise ValueError(f"Drum Essentials metadata mismatch for {field}: {item['path']}")
    family = metadata.get("family")
    if item["role"] == "drum_one_shot":
        if family not in DRUM_FAMILY_SPECS:
            raise ValueError(f"Drum Essentials source family is invalid: {item['path']}")
        variant = metadata.get("variant")
        if isinstance(variant, bool) or not isinstance(variant, int):
            raise ValueError(f"Drum Essentials source variant is invalid: {item['path']}")
        recipe = DrumEssentialsRecipe(**manifest["recipe"])
        voice = DrumVoiceRecipe(recipe, family, variant)
        if metadata.get("descriptor") != voice.descriptor:
            raise ValueError(f"Drum Essentials descriptor is invalid: {item['path']}")
        parameters = metadata.get("synthesis_parameters")
        if not isinstance(parameters, dict) or not parameters:
            raise ValueError(f"Drum Essentials synthesis metadata is incomplete: {item['path']}")
        for name, minimum, maximum in DRUM_FAMILY_SPECS[family].parameter_bounds:
            value = parameters.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
                raise ValueError(
                    f"Drum Essentials synthesis parameter {name} is outside its family bound: "
                    f"{item['path']}"
                )
    elif item["role"] == "preview" and family == "preview":
        if metadata.get("variant") != 1 or metadata.get("descriptor") != "AUDITION":
            raise ValueError(f"Drum Essentials preview identity is invalid: {item['path']}")
    else:
        raise ValueError(f"Drum Essentials WAV role is invalid: {item['path']}")
    result = validate_drum_wav(_path(root, item["path"]), family=family)
    result_fields = {
        "audio_shape_sha256": result["audio_shape_sha256"],
        "channels": result["channels"],
        "dc_offset": result["dc_offset"],
        "duration_seconds": result["duration_seconds"],
        "peak": result["peak"],
        "rms": result["rms"],
        "sample_rate": result["sample_rate"],
        "sample_width_bits": result["sample_width_bits"],
    }
    declared_fields = {
        "audio_shape_sha256": metadata.get("audio_shape_sha256"),
        "channels": metadata.get("channels"),
        "dc_offset": metadata.get("dc_offset"),
        "duration_seconds": metadata.get("duration_seconds"),
        "peak": metadata.get("peak"),
        "rms": metadata.get("rms"),
        "sample_rate": metadata.get("sample_rate"),
        "sample_width_bits": metadata.get("bit_depth"),
    }
    if declared_fields != result_fields:
        raise ValueError(f"Drum Essentials audio metadata disagrees with parsed WAV: {item['path']}")
    return result
