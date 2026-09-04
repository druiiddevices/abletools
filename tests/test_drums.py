import hashlib
import json
import math
import shutil
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

from abletools.drum_audio import (
    MAX_DC_OFFSET,
    MAX_PEAK,
    encode_pcm24_mono,
    read_pcm24_mono,
    render_drum_voice,
    validate_drum_wav,
    write_pcm24_mono,
)
from abletools.drum_pack import build_drum_essentials_pack
from abletools.drum_recipe import (
    DRUM_FAMILIES,
    DRUM_FAMILY_SPECS,
    DRUM_SOURCE_COUNT,
    DrumEssentialsRecipe,
    DrumVoiceRecipe,
)
from abletools.pack import validate_pack, validate_zip


class DrumAudioTests(unittest.TestCase):
    def test_recipe_models_bounds_and_family_rng_isolation(self) -> None:
        recipe = DrumEssentialsRecipe(seed=1842, style="DRUIID")
        self.assertEqual(DRUM_SOURCE_COUNT, 40)
        self.assertEqual(tuple(DRUM_FAMILY_SPECS), DRUM_FAMILIES)
        self.assertEqual(recipe.profile_version, "DRUIID_R1")
        changed_kick = DrumEssentialsRecipe(seed=1842, style="DRUIID", kick_character=0.9)
        self.assertNotEqual(recipe.family_seed_data("kick"), changed_kick.family_seed_data("kick"))
        self.assertEqual(recipe.family_seed_data("snare"), changed_kick.family_seed_data("snare"))
        self.assertEqual(
            render_drum_voice(DrumVoiceRecipe(recipe, "snare", 1)).samples,
            render_drum_voice(DrumVoiceRecipe(changed_kick, "snare", 1)).samples,
        )
        with self.assertRaisesRegex(ValueError, "mono 48 kHz"):
            DrumEssentialsRecipe(seed=1, style="HAZY", sample_rate=44_100)
        with self.assertRaisesRegex(ValueError, "style must"):
            DrumEssentialsRecipe(seed=1, style="OTHER")

    def test_voice_bytes_are_deterministic_and_seed_sensitive(self) -> None:
        first = render_drum_voice(
            DrumVoiceRecipe(DrumEssentialsRecipe(seed=91, style="HAZY"), "shaker", 3)
        )
        second = render_drum_voice(
            DrumVoiceRecipe(DrumEssentialsRecipe(seed=91, style="HAZY"), "shaker", 3)
        )
        changed = render_drum_voice(
            DrumVoiceRecipe(DrumEssentialsRecipe(seed=92, style="HAZY"), "shaker", 3)
        )
        self.assertEqual(encode_pcm24_mono(first.samples), encode_pcm24_mono(second.samples))
        self.assertNotEqual(encode_pcm24_mono(first.samples), encode_pcm24_mono(changed.samples))
        self.assertNotEqual(first.synthesis_parameters, changed.synthesis_parameters)

    def test_strict_validator_accepts_all_families_and_practical_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for family in DRUM_FAMILIES:
                voice = DrumVoiceRecipe(DrumEssentialsRecipe(seed=7, style="DRUIID"), family, 1)
                render = render_drum_voice(voice)
                path = write_pcm24_mono(root / f"{family}.wav", render.samples)
                result = validate_drum_wav(path, family=family)
                spec = DRUM_FAMILY_SPECS[family]
                self.assertTrue(spec.minimum_duration <= result["duration_seconds"] <= spec.maximum_duration)
                self.assertLessEqual(result["peak"], MAX_PEAK)
                self.assertLessEqual(abs(result["dc_offset"]), MAX_DC_OFFSET)
                self.assertGreater(result["rms"], 0.004)
                for name, minimum, maximum in spec.parameter_bounds:
                    self.assertTrue(
                        minimum <= render.synthesis_parameters[name] <= maximum,
                        f"{family}.{name}",
                    )

    def test_validator_rejects_format_truncation_and_nonfinite_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = render_drum_voice(
                DrumVoiceRecipe(DrumEssentialsRecipe(seed=8, style="DRUIID"), "kick", 1)
            ).samples
            valid = encode_pcm24_mono(samples)
            mutations = {
                "channels": (22, (2).to_bytes(2, "little")),
                "sample rate": (24, (44_100).to_bytes(4, "little")),
                "bit depth": (34, (16).to_bytes(2, "little")),
            }
            for name, (offset, replacement) in mutations.items():
                with self.subTest(name=name):
                    data = bytearray(valid)
                    data[offset : offset + len(replacement)] = replacement
                    path = root / f"wrong-{name}.wav"
                    path.write_bytes(data)
                    with self.assertRaisesRegex(ValueError, "mono 48 kHz, 24-bit PCM|malformed"):
                        validate_drum_wav(path, family="kick")
            truncated = root / "truncated.wav"
            truncated.write_bytes(valid[:-17])
            with self.assertRaisesRegex(ValueError, "truncated"):
                validate_drum_wav(truncated, family="kick")
            with self.assertRaisesRegex(ValueError, "finite"):
                write_pcm24_mono(root / "nan.wav", [0.0, float("nan"), 0.0])

    def test_validator_rejects_silence_clipping_dc_edges_and_long_silence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame_count = 14_400
            silent = write_pcm24_mono(root / "silent.wav", [0.0] * frame_count)
            with self.assertRaisesRegex(ValueError, "silent"):
                validate_drum_wav(silent, family="kick")

            clipped_samples = [0.0] + [math.sin(index * 0.2) for index in range(frame_count - 2)] + [0.0]
            clipped = write_pcm24_mono(root / "clipped.wav", clipped_samples)
            with self.assertRaisesRegex(ValueError, "clips|headroom"):
                validate_drum_wav(clipped, family="kick")

            dc_samples = [0.0] + [0.08 * math.sin(index * 0.1) + 0.02 for index in range(frame_count - 2)] + [0.0]
            dc = write_pcm24_mono(root / "dc.wav", dc_samples)
            with self.assertRaisesRegex(ValueError, "DC offset"):
                validate_drum_wav(dc, family="kick")

            voice = render_drum_voice(
                DrumVoiceRecipe(DrumEssentialsRecipe(seed=9, style="DRUIID"), "kick", 1)
            )
            broken_edge = list(voice.samples)
            broken_edge[0] = 0.2
            edge = write_pcm24_mono(root / "edge.wav", broken_edge)
            with self.assertRaisesRegex(ValueError, "boundary fade"):
                validate_drum_wav(edge, family="kick")

            long_silence = list(voice.samples) + [0.0] * 600
            trailing = write_pcm24_mono(root / "trailing.wav", long_silence)
            with self.assertRaisesRegex(ValueError, "trailing silence"):
                validate_drum_wav(trailing, family="kick")


class DrumPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.packs = {
            style: build_drum_essentials_pack(
                cls.root / style.lower(), DrumEssentialsRecipe(seed=1842, style=style)
            )
            for style in ("DRUIID", "HAZY")
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @staticmethod
    def _manifest(root: Path) -> dict[str, object]:
        return json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    @staticmethod
    def _roughness(root: Path, manifest: dict[str, object]) -> float:
        values: list[float] = []
        for item in manifest["files"]:
            if item["role"] != "drum_one_shot":
                continue
            samples = read_pcm24_mono(root / item["path"])[0]
            values.append(sum(abs(current - previous) for previous, current in zip(samples, samples[1:])) / (len(samples) - 1))
        return sum(values) / len(values)

    def test_exact_catalog_and_all_eighty_source_wavs_are_unique(self) -> None:
        all_hashes: list[str] = []
        all_shape_hashes: list[str] = []
        for style, root in self.packs.items():
            manifest = self._manifest(root)
            sources = [item for item in manifest["files"] if item["role"] == "drum_one_shot"]
            previews = [item for item in manifest["files"] if item["role"] == "preview"]
            self.assertEqual(len(sources), 40)
            self.assertEqual(len(previews), 1)
            self.assertEqual(
                {family: sum(item["metadata"]["family"] == family for item in sources) for family in DRUM_FAMILIES},
                {family: spec.count for family, spec in DRUM_FAMILY_SPECS.items()},
            )
            self.assertTrue(all(item["path"].startswith(f"WAV/") for item in sources))
            self.assertTrue(all(Path(item["path"]).name.startswith(style) for item in sources))
            all_hashes.extend(item["sha256"] for item in sources)
            shape_hashes = [item["metadata"]["audio_shape_sha256"] for item in sources]
            self.assertEqual(len(set(shape_hashes)), 40)
            all_shape_hashes.extend(shape_hashes)
        self.assertEqual(len(all_hashes), 80)
        self.assertEqual(len(set(all_hashes)), 80)
        self.assertEqual(len(set(all_shape_hashes)), 80)

    def test_both_styles_are_byte_deterministic_in_wavs_manifests_and_zips(self) -> None:
        for style, first in self.packs.items():
            with self.subTest(style=style):
                second = build_drum_essentials_pack(
                    self.root / f"{style.lower()}-again",
                    DrumEssentialsRecipe(seed=1842, style=style),
                )
                self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())
                self.assertEqual(first.with_suffix(".zip").read_bytes(), second.with_suffix(".zip").read_bytes())
                manifest = self._manifest(first)
                for item in manifest["files"]:
                    self.assertEqual((first / item["path"]).read_bytes(), (second / item["path"]).read_bytes())

    def test_style_profiles_are_measurably_distinct_without_filenames(self) -> None:
        druiid_manifest = self._manifest(self.packs["DRUIID"])
        hazy_manifest = self._manifest(self.packs["HAZY"])
        druiid_roughness = self._roughness(self.packs["DRUIID"], druiid_manifest)
        hazy_roughness = self._roughness(self.packs["HAZY"], hazy_manifest)
        druiid_duration = sum(
            item["metadata"]["duration_seconds"]
            for item in druiid_manifest["files"]
            if item["role"] == "drum_one_shot"
        ) / 40
        hazy_duration = sum(
            item["metadata"]["duration_seconds"]
            for item in hazy_manifest["files"]
            if item["role"] == "drum_one_shot"
        ) / 40
        self.assertLess(hazy_roughness, druiid_roughness * 0.70)
        self.assertGreater(hazy_duration, druiid_duration)

    def test_previews_use_only_included_material_and_directory_zip_validation_agree(self) -> None:
        for style, root in self.packs.items():
            with self.subTest(style=style):
                manifest = self._manifest(root)
                source_paths = {
                    item["path"] for item in manifest["files"] if item["role"] == "drum_one_shot"
                }
                preview = next(item for item in manifest["files"] if item["role"] == "preview")
                referenced = {
                    placement["source"]
                    for placement in preview["metadata"]["source_assembly"]["placements"]
                }
                self.assertTrue(referenced)
                self.assertLessEqual(referenced, source_paths)
                directory = validate_pack(root)
                archive = validate_zip(root.with_suffix(".zip"))
                self.assertEqual(directory, archive["result"])
                self.assertEqual(archive["files"], 41)

    def test_pack_rejects_duplicate_audio_and_metadata_disagreement(self) -> None:
        for defect in ("duplicate", "gain_duplicate", "metadata"):
            with self.subTest(defect=defect):
                root = self.root / f"broken-{defect}"
                shutil.copytree(self.packs["DRUIID"], root)
                manifest = self._manifest(root)
                sources = [item for item in manifest["files"] if item["role"] == "drum_one_shot"]
                if defect in {"duplicate", "gain_duplicate"}:
                    first, second = sources[0], sources[1]
                    if defect == "duplicate":
                        (root / second["path"]).write_bytes((root / first["path"]).read_bytes())
                    else:
                        samples = read_pcm24_mono(root / first["path"])[0]
                        write_pcm24_mono(root / second["path"], (sample * 0.75 for sample in samples))
                    result = validate_drum_wav(root / second["path"], family="kick")
                    second["sha256"] = hashlib.sha256((root / second["path"]).read_bytes()).hexdigest()
                    second_record = next(item for item in manifest["validation"] if item["file"] == second["path"])
                    second_record["result"] = result
                    for key, value in result.items():
                        metadata_key = "bit_depth" if key == "sample_width_bits" else key
                        if metadata_key in second["metadata"]:
                            second["metadata"][metadata_key] = value
                    message = "duplicate source audio hashes" if defect == "duplicate" else "gain-only duplicate"
                    with self.assertRaisesRegex(ValueError, message):
                        (root / "manifest.json").write_text(
                            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                        )
                        validate_pack(root)
                else:
                    sources[0]["metadata"]["style"] = "HAZY"
                    (root / "manifest.json").write_text(
                        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                    )
                    with self.assertRaisesRegex(ValueError, "metadata mismatch for style"):
                        validate_pack(root)

    def test_preview_tampering_and_nondeterministic_zip_metadata_fail_closed(self) -> None:
        root = self.root / "broken-preview"
        shutil.copytree(self.packs["HAZY"], root)
        manifest = self._manifest(root)
        preview = next(item for item in manifest["files"] if item["role"] == "preview")
        preview["metadata"]["source_assembly"]["placements"][0]["gain"] = 0.1
        (root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "not reconstructible"):
            validate_pack(root)

        source = self.packs["DRUIID"].with_suffix(".zip")
        volatile = self.root / "volatile.zip"
        with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(volatile, "w") as changed:
            for info in original.infolist():
                replacement = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 2, 3, 4, 6))
                replacement.external_attr = info.external_attr
                replacement.create_system = info.create_system
                changed.writestr(replacement, original.read(info.filename))
        with self.assertRaisesRegex(ValueError, "metadata is not deterministic"):
            validate_zip(volatile)


if __name__ == "__main__":
    unittest.main()
