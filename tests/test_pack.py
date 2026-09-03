import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from abletools.pack import (
    build_demo_pack,
    build_druiid_midi_pack,
    validate_pack,
    validate_zip,
)
from abletools.recipe import MidiEssentialsRecipe


class PackTests(unittest.TestCase):
    def test_demo_pack_builds_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "demo"
            build_demo_pack(root, 1842)
            results = validate_pack(root)
            self.assertEqual(len(results), 2)
            self.assertEqual(validate_zip(root.with_suffix(".zip"))["files"], 2)

    def test_druiid_pack_is_complete_and_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe = MidiEssentialsRecipe(seed=1842)
            first = build_druiid_midi_pack(parent / "first", recipe)
            second = build_druiid_midi_pack(parent / "second", recipe)
            first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            second_manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(first_manifest["files"]), 12)
            self.assertEqual(first_manifest, second_manifest)
            self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())
            for item in first_manifest["files"]:
                self.assertEqual((first / item["path"]).read_bytes(), (second / item["path"]).read_bytes())
            self.assertEqual(first.with_suffix(".zip").read_bytes(), second.with_suffix(".zip").read_bytes())
            self.assertEqual(validate_zip(first.with_suffix(".zip"))["files"], 12)

    def test_corrupt_binary_and_stale_validation_record_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = build_druiid_midi_pack(Path(directory) / "pack", MidiEssentialsRecipe(seed=7))
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            asset = root / manifest["files"][0]["path"]
            original = asset.read_bytes()
            asset.write_bytes(original + b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                validate_pack(root)
            asset.write_bytes(original)
            manifest["validation"][0]["result"]["notes"] += 1
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale validation record"):
                validate_pack(root)

    def test_extra_pack_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = build_druiid_midi_pack(Path(directory) / "pack", MidiEssentialsRecipe(seed=8))
            (root / "unexpected.txt").write_text("not inventoried", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                validate_pack(root)

    def test_unsafe_zip_path_is_rejected_without_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape.txt", "unsafe")
            with self.assertRaisesRegex(ValueError, "relative and contained"):
                validate_zip(archive)
            self.assertFalse((Path(directory).parent / "escape.txt").exists())

    def test_corrupt_zip_member_fails_checksum_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = build_druiid_midi_pack(Path(directory) / "pack", MidiEssentialsRecipe(seed=10))
            source = root.with_suffix(".zip")
            corrupt = Path(directory) / "corrupt.zip"
            with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(corrupt, "w") as changed:
                target = next(name for name in original.namelist() if name.endswith(".mid"))
                for info in original.infolist():
                    data = original.read(info.filename)
                    changed.writestr(info, data + b"corrupt" if info.filename == target else data)
            with self.assertRaisesRegex(ValueError, "ZIP checksum mismatch"):
                validate_zip(corrupt)


if __name__ == "__main__":
    unittest.main()
