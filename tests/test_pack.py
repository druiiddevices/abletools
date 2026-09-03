import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from abletools.manifest import write_manifest
from abletools.pack import (
    build_demo_pack,
    build_druiid_midi_pack,
    validate_pack,
    validate_zip,
)
from abletools.recipe import MidiEssentialsRecipe


class PackTests(unittest.TestCase):
    @staticmethod
    def _load_manifest(root: Path) -> dict[str, object]:
        return json.loads((root / "manifest.json").read_text(encoding="utf-8"))

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

    def test_pack_rejects_declared_ppq_and_midi_format_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = build_druiid_midi_pack(Path(directory) / "pack", MidiEssentialsRecipe(seed=11))
            original = self._load_manifest(root)
            for field, value, message in (
                ("ppq", 960, "MIDI PPQ mismatch"),
                ("midi_format", 1, "MIDI format mismatch"),
            ):
                with self.subTest(field=field):
                    manifest = json.loads(json.dumps(original))
                    manifest["files"][0]["format"][field] = value
                    write_manifest(root / "manifest.json", manifest)
                    with self.assertRaisesRegex(ValueError, message):
                        validate_pack(root)
            write_manifest(root / "manifest.json", original)

    def test_pack_rejects_top_level_and_asset_metadata_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = build_druiid_midi_pack(Path(directory) / "pack", MidiEssentialsRecipe(seed=12))
            manifest = self._load_manifest(root)
            manifest["files"][0]["metadata"]["key"] = "C major"
            write_manifest(root / "manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "MIDI metadata mismatch for key"):
                validate_pack(root)

    def test_pack_rejects_incomplete_or_malformed_chord_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = build_druiid_midi_pack(Path(directory) / "pack", MidiEssentialsRecipe(seed=13))
            original = self._load_manifest(root)
            chord_index = next(
                index for index, item in enumerate(original["files"]) if item["role"] == "chords"
            )

            missing = json.loads(json.dumps(original))
            del missing["files"][chord_index]["metadata"]["chord_symbols"]
            write_manifest(root / "manifest.json", missing)
            with self.assertRaisesRegex(ValueError, "requires non-empty chord symbols"):
                validate_pack(root)

            malformed = json.loads(json.dumps(original))
            malformed["files"][chord_index]["metadata"]["degree_sequence"] = [1, 6]
            write_manifest(root / "manifest.json", malformed)
            with self.assertRaisesRegex(ValueError, "matching lengths"):
                validate_pack(root)

    def test_pack_rejects_drum_channel_and_mapping_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = build_druiid_midi_pack(Path(directory) / "pack", MidiEssentialsRecipe(seed=14))
            original = self._load_manifest(root)
            drum_index = next(
                index
                for index, item in enumerate(original["files"])
                if item["role"] == "drum_pattern" and item["metadata"]["variation"] == "A"
            )

            wrong_channel = json.loads(json.dumps(original))
            wrong_channel["files"][drum_index]["metadata"]["channel"] = 9
            write_manifest(root / "manifest.json", wrong_channel)
            with self.assertRaisesRegex(ValueError, "declared channel"):
                validate_pack(root)

            wrong_mapping = json.loads(json.dumps(original))
            wrong_mapping["files"][drum_index]["metadata"]["drum_mapping"]["open_hat"] = 44
            write_manifest(root / "manifest.json", wrong_mapping)
            with self.assertRaisesRegex(ValueError, "drum mapping must match"):
                validate_pack(root)

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
