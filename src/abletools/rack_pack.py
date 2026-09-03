"""Deterministic packs of validated Ableton rack blueprint JSON files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .capabilities import require_capability
from .manifest import write_manifest
from .pack import _sha256, _write_readme, validate_pack, validate_zip, write_deterministic_zip
from .rack_blueprint import RACK_FAMILIES, RackBlueprintRecipe, generate_rack_blueprints, write_blueprint
from .rack_validation import validate_rack_blueprint_file


def _filename(blueprint: dict[str, Any]) -> str:
    return f"{blueprint['style']}_{blueprint['family']}_S{blueprint['seed']:04d}_V01.json"


def _readme(recipe: RackBlueprintRecipe, blueprints: list[dict[str, Any]]) -> str:
    lines = [
        f"# {recipe.style} Ableton Rack Blueprint Foundation",
        "",
        "> **VALIDATED BUILD SPECIFICATIONS — NOT ABLETON `.adg`, `.adv`, `.agr`, OR `.amxd` FILES.**",
        "",
        "These deterministic JSON documents describe how to construct and review stock-device racks in Ableton Live 12.",
        "They have passed Abletools schema, registry, routing, macro, range, safety, manifest, checksum, and packaging validation.",
        "They have not been opened or auditioned in Ableton Live because native serialization remains capability-gated.",
        "",
        "## Inventory",
        "",
    ]
    for blueprint in blueprints:
        device_count = sum(len(chain["devices"]) for chain in blueprint["topology"]["chains"])
        lines.append(
            f"- `{_filename(blueprint)}` — {blueprint['rack_type']}; "
            f"{device_count} devices; {len(blueprint['macros'])} macros."
        )
    lines.extend(
        [
            "",
            "## Construction boundary",
            "",
            "Only device and parameter names in the closed Abletools Live 12 registry are accepted. Rebuild each specification manually in Live, then perform open, listening, level, mono/stereo, latency, tail, and bypass checks before treating it as an approved native asset.",
            "",
            "Output/limiter safety settings and the OUT macro are excluded from randomization. MIDI blueprints contain MIDI devices only and describe bounded note behavior.",
            "",
        ]
    )
    return "\n".join(lines)


def build_rack_blueprint_pack(output: str | Path, recipe: RackBlueprintRecipe) -> Path:
    """Build, validate, and ZIP the exact five-blueprint Milestone 3A catalog."""
    require_capability("ableton_rack_blueprint")
    require_capability("zip_pack")
    root = Path(output)
    blueprint_root = root / "RACKS" / "BLUEPRINTS"
    blueprints = generate_rack_blueprints(recipe)
    if tuple(blueprint["family"] for blueprint in blueprints) != RACK_FAMILIES:
        raise ValueError("rack blueprint generator did not produce the exact Milestone 3A catalog")
    files: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    for blueprint in blueprints:
        path = write_blueprint(blueprint_root / _filename(blueprint), blueprint)
        result = validate_rack_blueprint_file(path)
        relative = path.relative_to(root).as_posix()
        role = "rack_blueprint"
        files.append(
            {
                "path": relative,
                "role": role,
                "sha256": _sha256(path),
                "format": {
                    "container": "Abletools Rack Blueprint JSON",
                    "media_type": "application/json",
                    "schema_version": blueprint["schema_version"],
                },
                "metadata": {
                    "device_count": result["devices"],
                    "family": blueprint["family"],
                    "macro_count": result["macros"],
                    "minimum_live_version": blueprint["minimum_live_version"],
                    "native_format": False,
                    "rack_type": blueprint["rack_type"],
                    "role": role,
                    "seed": recipe.seed,
                    "style": recipe.style,
                },
            }
        )
        validations.append({"file": relative, "validator": "abletools.rack_blueprint", "result": result})
    manifest = {
        "schema_version": "1.0.0",
        "pack_name": f"{recipe.style}_RACK_BLUEPRINT_FOUNDATION_S{recipe.seed:04d}",
        "version": "1.0.0",
        "generator_version": __version__,
        "style": recipe.style,
        "asset_type": "ableton_rack_blueprints",
        "seed": recipe.seed,
        "profile_version": f"{recipe.style}_R1",
        "recipe": recipe.canonical_data(),
        "files": files,
        "format": {
            "container": "Abletools Rack Blueprint JSON",
            "media_type": "application/json",
            "native_format": False,
            "schema_version": "1.0.0",
        },
        "generation_notes": [
            "Deterministic JSON build specifications using verified stock-device vocabulary.",
            "Schema, registry, topology, macro, variation, safety, checksum, inventory, and ZIP validation completed.",
            "Native Ableton serialization, Ableton-open verification, and listening approval remain gated.",
        ],
        "validation": validations,
        "dependencies": ["Ableton Live 12 stock devices for manual reconstruction only"],
    }
    _write_readme(root / "README.md", _readme(recipe, blueprints))
    write_manifest(root / "manifest.json", manifest)
    validate_pack(root)
    archive = write_deterministic_zip(root, root.with_suffix(".zip"))
    validate_zip(archive)
    return root
