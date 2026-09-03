"""Strict asset-manifest creation and dependency-free validation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "1.0.0"
REQUIRED_FIELDS = {
    "schema_version",
    "pack_name",
    "version",
    "generator_version",
    "style",
    "asset_type",
    "seed",
    "files",
    "format",
    "generation_notes",
    "validation",
    "dependencies",
}
ALLOWED_FIELDS = REQUIRED_FIELDS | {
    "tempo_bpm",
    "meter",
    "key",
    "root",
    "scale",
    "bars",
    "profile_version",
    "recipe",
}
ALLOWED_STYLES = {"DRUIID", "HAZY"}
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
FILE_FIELDS = {"path", "role", "sha256", "format", "metadata"}
VALIDATION_FIELDS = {"file", "validator", "result"}


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_relative_path(value: str) -> PurePosixPath:
    """Validate and normalize one portable, contained manifest path."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("manifest paths must be non-empty POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("manifest file paths must be relative and contained")
    if ":" in path.parts[0]:
        raise ValueError("manifest file paths cannot contain a drive prefix")
    if str(path) != value:
        raise ValueError("manifest file paths must use canonical POSIX spelling")
    return path


def _validate_file_entry(item: Any) -> str:
    if not isinstance(item, dict):
        raise ValueError("every file entry must be an object")
    missing = FILE_FIELDS - item.keys()
    unknown = item.keys() - FILE_FIELDS
    if missing:
        raise ValueError(f"file entry missing required fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"file entry contains unknown fields: {', '.join(sorted(unknown))}")
    path = str(validate_relative_path(item["path"]))
    if not isinstance(item["role"], str) or not item["role"]:
        raise ValueError("file role must be a non-empty string")
    if not isinstance(item["sha256"], str) or not SHA256.fullmatch(item["sha256"]):
        raise ValueError("file sha256 must be 64 lowercase hexadecimal characters")
    if not isinstance(item["format"], dict) or not item["format"]:
        raise ValueError("file format must be a non-empty object")
    if not isinstance(item["metadata"], dict) or not item["metadata"]:
        raise ValueError("file metadata must be a non-empty object")
    if item["metadata"].get("role") != item["role"]:
        raise ValueError("file metadata role must match the file role")
    if isinstance(item["metadata"].get("seed"), bool) or not isinstance(item["metadata"].get("seed"), int):
        raise ValueError("file metadata requires an integer seed")
    return path


def _validate_validation_entry(item: Any) -> str:
    if not isinstance(item, dict):
        raise ValueError("every validation entry must be an object")
    missing = VALIDATION_FIELDS - item.keys()
    unknown = item.keys() - VALIDATION_FIELDS
    if missing:
        raise ValueError(f"validation entry missing required fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"validation entry contains unknown fields: {', '.join(sorted(unknown))}")
    path = str(validate_relative_path(item["file"]))
    if not isinstance(item["validator"], str) or not item["validator"]:
        raise ValueError("validation entry requires a validator name")
    if not isinstance(item["result"], dict) or not item["result"]:
        raise ValueError("validation entry requires a non-empty result object")
    return path


def validate_manifest_data(data: dict[str, Any], root: str | Path | None = None) -> None:
    """Validate the complete R1 manifest contract and optional file inventory."""
    if not isinstance(data, dict):
        raise ValueError("manifest must contain a JSON object")
    missing = sorted(REQUIRED_FIELDS - data.keys())
    unknown = sorted(data.keys() - ALLOWED_FIELDS)
    if missing:
        raise ValueError(f"manifest missing required fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"manifest contains unknown fields: {', '.join(unknown)}")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(data["pack_name"], str) or not SAFE_NAME.fullmatch(data["pack_name"]):
        raise ValueError("pack_name must be a filesystem-safe identifier")
    if not isinstance(data["version"], str) or not SEMVER.fullmatch(data["version"]):
        raise ValueError("version must be semantic version text")
    if not isinstance(data["generator_version"], str) or not SEMVER.fullmatch(data["generator_version"]):
        raise ValueError("generator_version must be semantic version text")
    if data["style"] not in ALLOWED_STYLES:
        raise ValueError("style must be DRUIID or HAZY")
    if not isinstance(data["asset_type"], str) or not data["asset_type"]:
        raise ValueError("asset_type must be a non-empty string")
    if isinstance(data["seed"], bool) or not isinstance(data["seed"], int):
        raise ValueError("seed must be an integer")
    if not isinstance(data["files"], list) or not data["files"]:
        raise ValueError("files must be a non-empty list")
    if not isinstance(data["format"], dict) or not data["format"]:
        raise ValueError("format must be a non-empty object")
    if not isinstance(data["generation_notes"], list) or any(
        not isinstance(note, str) or not note for note in data["generation_notes"]
    ):
        raise ValueError("generation_notes must contain non-empty strings")
    if not isinstance(data["dependencies"], list) or any(
        not isinstance(dependency, str) or not dependency for dependency in data["dependencies"]
    ):
        raise ValueError("dependencies must contain non-empty strings")
    if not isinstance(data["validation"], list):
        raise ValueError("validation must be a list")

    if "tempo_bpm" in data and (not _is_number(data["tempo_bpm"]) or data["tempo_bpm"] <= 0):
        raise ValueError("tempo_bpm must be positive")
    if "bars" in data and (
        isinstance(data["bars"], bool) or not isinstance(data["bars"], int) or data["bars"] <= 0
    ):
        raise ValueError("bars must be a positive integer")
    for field in ("meter", "key", "root", "scale", "profile_version"):
        if field in data and (not isinstance(data[field], str) or not data[field]):
            raise ValueError(f"{field} must be a non-empty string")
    if "recipe" in data and not isinstance(data["recipe"], dict):
        raise ValueError("recipe must be an object")

    file_paths = [_validate_file_entry(item) for item in data["files"]]
    if len(file_paths) != len({path.casefold() for path in file_paths}):
        raise ValueError("manifest file paths must be unique")
    validation_paths = [_validate_validation_entry(item) for item in data["validation"]]
    if len(validation_paths) != len({path.casefold() for path in validation_paths}):
        raise ValueError("validation records must cover each file exactly once")
    if set(validation_paths) != set(file_paths):
        raise ValueError("validation records must exactly cover the file inventory")

    midi_files = [item for item in data["files"] if PurePosixPath(item["path"]).suffix.lower() in {".mid", ".midi"}]
    if midi_files:
        midi_fields = {"tempo_bpm", "meter", "key", "bars", "profile_version", "recipe"}
        missing_midi = sorted(midi_fields - data.keys())
        if missing_midi:
            raise ValueError(f"MIDI manifest missing required fields: {', '.join(missing_midi)}")
        if data["meter"] != "4/4":
            raise ValueError("R1 MIDI packs must declare 4/4 meter")

    if root is not None:
        pack_root = Path(root).resolve()
        for item in data["files"]:
            relative = Path(*PurePosixPath(item["path"]).parts)
            candidate = (pack_root / relative).resolve()
            if not candidate.is_relative_to(pack_root) or not candidate.is_file():
                raise ValueError(f"manifest file is missing or escapes its pack: {item['path']}")
            if item["sha256"] != _sha256(candidate):
                raise ValueError(f"checksum mismatch: {item['path']}")


def write_manifest(path: str | Path, data: dict[str, Any]) -> Path:
    validate_manifest_data(data)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return output


def load_manifest(path: str | Path, *, check_files: bool = True) -> dict[str, Any]:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest_data(data, manifest_path.parent if check_files else None)
    return data
