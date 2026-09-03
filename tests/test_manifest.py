import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from abletools.manifest import REQUIRED_FIELDS, load_manifest, validate_manifest_data, write_manifest


def manifest_data(asset: bytes = b"placeholder") -> dict[str, object]:
    digest = hashlib.sha256(asset).hexdigest()
    return {
        "schema_version": "1.0.0",
        "pack_name": "test",
        "version": "1.0.0",
        "generator_version": "0.2.0",
        "style": "DRUIID",
        "asset_type": "midi",
        "seed": 1,
        "tempo_bpm": 120,
        "meter": "4/4",
        "key": "A minor",
        "bars": 4,
        "profile_version": "DRUIID_R1",
        "recipe": {"seed": 1},
        "files": [
            {
                "path": "asset.mid",
                "role": "test",
                "sha256": digest,
                "format": {"container": "Standard MIDI File"},
                "metadata": {"role": "test", "seed": 1},
            }
        ],
        "format": {"container": "Standard MIDI File"},
        "generation_notes": [],
        "validation": [
            {"file": "asset.mid", "validator": "abletools.midi", "result": {"notes": 1}}
        ],
        "dependencies": [],
    }


class ManifestTests(unittest.TestCase):
    def test_published_schema_matches_runtime_required_fields(self) -> None:
        schema_path = Path(__file__).parents[1] / "schemas" / "asset-manifest.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(set(schema["required"]), REQUIRED_FIELDS)
        self.assertFalse(schema["additionalProperties"])

    def test_manifest_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "asset.mid").write_bytes(b"placeholder")
            path = write_manifest(root / "manifest.json", manifest_data())
            self.assertEqual(load_manifest(path)["style"], "DRUIID")

    def test_unknown_style_is_rejected(self) -> None:
        data = manifest_data()
        data["style"] = "BOC"
        with self.assertRaisesRegex(ValueError, "DRUIID or HAZY"):
            validate_manifest_data(data)

    def test_validation_must_cover_inventory(self) -> None:
        data = manifest_data()
        data["validation"] = []
        with self.assertRaisesRegex(ValueError, "exactly cover"):
            validate_manifest_data(data)

    def test_checksum_is_verified_when_files_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "asset.mid").write_bytes(b"changed")
            path = write_manifest(root / "manifest.json", manifest_data())
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_manifest(path)

    def test_unsafe_manifest_path_is_rejected(self) -> None:
        data = manifest_data()
        data["files"][0]["path"] = "../asset.mid"
        data["validation"][0]["file"] = "../asset.mid"
        with self.assertRaisesRegex(ValueError, "relative and contained"):
            validate_manifest_data(data)


if __name__ == "__main__":
    unittest.main()
