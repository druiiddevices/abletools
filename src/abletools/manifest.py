"""Asset manifest creation and dependency-free validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "schema_version",
    "pack_name",
    "version",
    "style",
    "asset_type",
    "seed",
    "files",
    "validation",
}
ALLOWED_STYLES = {"DRUIID", "HAZY"}


def validate_manifest_data(data: dict[str, Any], root: str | Path | None = None) -> None:
    missing = sorted(REQUIRED_FIELDS - data.keys())
    if missing:
        raise ValueError(f"manifest missing required fields: {', '.join(missing)}")
    if data["style"] not in ALLOWED_STYLES:
        raise ValueError("style must be DRUIID or HAZY")
    if isinstance(data["seed"], bool) or not isinstance(data["seed"], int):
        raise ValueError("seed must be an integer")
    if not isinstance(data["files"], list) or not data["files"]:
        raise ValueError("files must be a non-empty list")
    if not isinstance(data["validation"], list):
        raise ValueError("validation must be a list")
    seen: set[str] = set()
    for item in data["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item.get("role"):
            raise ValueError("every file entry requires path and role")
        path = item["path"]
        if path.startswith(("/", "\\")) or ".." in Path(path).parts:
            raise ValueError("manifest file paths must be relative and contained")
        if path in seen:
            raise ValueError(f"duplicate manifest path: {path}")
        seen.add(path)
        if root is not None and not (Path(root) / path).is_file():
            raise ValueError(f"manifest file is missing: {path}")


def write_manifest(path: str | Path, data: dict[str, Any]) -> Path:
    validate_manifest_data(data)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def load_manifest(path: str | Path, *, check_files: bool = True) -> dict[str, Any]:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest_data(data, manifest_path.parent if check_files else None)
    return data
