import tempfile
import unittest
from pathlib import Path

from abletools.manifest import load_manifest, validate_manifest_data, write_manifest


class ManifestTests(unittest.TestCase):
    def test_manifest_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "asset.mid").write_bytes(b"placeholder")
            data = {
                "schema_version": "1.0.0",
                "pack_name": "test",
                "version": "1.0.0",
                "style": "DRUIID",
                "asset_type": "midi",
                "seed": 1,
                "files": [{"path": "asset.mid", "role": "test"}],
                "validation": [],
            }
            path = write_manifest(root / "manifest.json", data)
            self.assertEqual(load_manifest(path)["style"], "DRUIID")

    def test_unknown_style_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_manifest_data({
                "schema_version": "1.0.0", "pack_name": "x", "version": "1.0.0",
                "style": "BOC", "asset_type": "midi", "seed": 1,
                "files": [{"path": "x.mid", "role": "test"}], "validation": [],
            })


if __name__ == "__main__":
    unittest.main()
