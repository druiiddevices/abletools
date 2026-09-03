import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from abletools.druiid import generate_midi_essentials
from abletools.hazy import HAZY_GM_DRUM_MAPPING, generate_hazy_midi_essentials
from abletools.manifest import write_manifest
from abletools.midi import BEATS_PER_BAR, PPQ
from abletools.pack import build_hazy_midi_pack, validate_pack, validate_zip
from abletools.recipe import HAZY_MODES, HazyMidiRecipe, MidiEssentialsRecipe


class HazyGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recipe = HazyMidiRecipe(seed=1842)
        self.assets = generate_hazy_midi_essentials(self.recipe)

    def test_pack_catalog_has_fifteen_related_abc_clips(self) -> None:
        self.assertEqual(len(self.assets), 15)
        by_role = {}
        for asset in self.assets:
            by_role.setdefault(asset.role, {})[asset.variation] = asset
        self.assertEqual(
            set(by_role), {"chords", "bass", "motif", "arpeggio", "drum_pattern"}
        )
        for role, variations in by_role.items():
            with self.subTest(role=role):
                self.assertEqual(set(variations), {"A", "B", "C"})
                self.assertEqual(
                    variations["A"].metadata["degree_sequence"],
                    variations["B"].metadata["degree_sequence"],
                )
                self.assertEqual(
                    variations["A"].metadata["degree_sequence"],
                    variations["C"].metadata["degree_sequence"],
                )
                self.assertNotEqual(variations["A"].notes, variations["B"].notes)
                self.assertNotEqual(variations["A"].notes, variations["C"].notes)
                self.assertNotEqual(variations["B"].notes, variations["C"].notes)
        motif = by_role["motif"]
        arpeggio = by_role["arpeggio"]
        self.assertEqual(
            {tuple(asset.metadata["motif_degree_cell"]) for asset in motif.values()},
            {tuple(motif["A"].metadata["motif_degree_cell"])},
        )
        self.assertEqual(
            {tuple(asset.metadata["arpeggio_degree_cell"]) for asset in arpeggio.values()},
            {tuple(arpeggio["A"].metadata["arpeggio_degree_cell"])},
        )

    def test_hazy_generation_is_not_a_relabelled_druiid_generator(self) -> None:
        progression = (1, 6, 4, 5)
        hazy = generate_hazy_midi_essentials(
            HazyMidiRecipe(
                seed=1842,
                root="A",
                mode="minor",
                bpm=120,
                bars=8,
                progression=progression,
            )
        )
        druiid = generate_midi_essentials(
            MidiEssentialsRecipe(
                seed=1842,
                root="A",
                scale="minor",
                bpm=120,
                bars=8,
                progression=progression,
            )
        )
        hazy_by_identity = {(asset.role, asset.variation): asset.notes for asset in hazy}
        druiid_by_identity = {(asset.role, asset.variation): asset.notes for asset in druiid}
        shared = set(hazy_by_identity) & set(druiid_by_identity)
        self.assertEqual(len(shared), 12)
        self.assertTrue(
            all(hazy_by_identity[identity] != druiid_by_identity[identity] for identity in shared)
        )
        with self.assertRaisesRegex(ValueError, "DRUIID style"):
            MidiEssentialsRecipe(seed=1, style="HAZY")
        with self.assertRaisesRegex(ValueError, "HAZY style"):
            HazyMidiRecipe(seed=1, style="DRUIID")

    def test_default_harmony_has_restrained_color_and_accurate_relationship_metadata(self) -> None:
        chords = [asset for asset in self.assets if asset.role == "chords"]
        self.assertTrue(
            any(
                color not in {"triad"}
                for asset in chords
                for color in asset.metadata["color_behavior"]
            )
        )
        self.assertTrue(
            any("triad" in asset.metadata["color_behavior"] for asset in chords)
        )
        for asset in chords:
            with self.subTest(variation=asset.variation):
                voicings = asset.metadata["voicings"]
                expected_exact = [
                    len(set(previous) & set(current))
                    for previous, current in zip(voicings, voicings[1:])
                ]
                expected_pitch_classes = [
                    len({note % 12 for note in previous} & {note % 12 for note in current})
                    for previous, current in zip(voicings, voicings[1:])
                ]
                self.assertEqual(
                    asset.metadata["voice_leading"]["exact_common_tone_counts"], expected_exact
                )
                self.assertEqual(
                    asset.metadata["voice_leading"]["pitch_class_common_tone_counts"],
                    expected_pitch_classes,
                )
                self.assertTrue(any(count > 0 for count in expected_pitch_classes))
                pedal = asset.metadata["pedal"]
                for chord_index in pedal["chord_indices"]:
                    self.assertIn(pedal["midi_note"], voicings[chord_index])
                tension_event = asset.metadata["tension_event"]
                if tension_event is not None:
                    tension_voicing = voicings[tension_event["chord_index"]]
                    self.assertLess(tension_voicing[0], tension_event["midi_note"])
                    self.assertLess(tension_event["midi_note"], tension_voicing[-1])

    def test_borrowed_tone_metadata_exactly_matches_generated_notes(self) -> None:
        root_pc = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B").index(
            self.recipe.root
        )
        allowed = {(root_pc + interval) % 12 for interval in HAZY_MODES[self.recipe.mode]}
        declarations = 0
        for asset in self.assets:
            if asset.role == "drum_pattern":
                self.assertEqual(asset.metadata["borrowed_tones"], [])
                continue
            actual = {note.note for note in asset.notes if note.note % 12 not in allowed}
            declared = {entry["midi_note"] for entry in asset.metadata["borrowed_tones"]}
            declarations += len(declared)
            self.assertEqual(actual, declared)
        self.assertGreater(declarations, 0)

    def test_role_specific_controls_leave_unrelated_roles_byte_inputs_unchanged(self) -> None:
        controls = {
            "chord_mutation": "chords",
            "bass_mutation": "bass",
            "motif_mutation": "motif",
            "arpeggio_mutation": "arpeggio",
            "drum_mutation": "drum_pattern",
        }
        for control, target_role in controls.items():
            with self.subTest(control=control):
                low = generate_hazy_midi_essentials(dataclasses.replace(self.recipe, **{control: 0.0}))
                high = generate_hazy_midi_essentials(dataclasses.replace(self.recipe, **{control: 1.0}))
                low_by_role = {
                    role: [asset.notes for asset in low if asset.role == role]
                    for role in {asset.role for asset in low}
                }
                high_by_role = {
                    role: [asset.notes for asset in high if asset.role == role]
                    for role in {asset.role for asset in high}
                }
                self.assertNotEqual(low_by_role[target_role], high_by_role[target_role])
                for role in low_by_role.keys() - {target_role}:
                    self.assertEqual(low_by_role[role], high_by_role[role])

    def test_zero_role_mutation_collapses_every_role_to_identical_abc_notes(self) -> None:
        recipe = HazyMidiRecipe(
            seed=1842,
            chord_mutation=0.0,
            bass_mutation=0.0,
            motif_mutation=0.0,
            arpeggio_mutation=0.0,
            drum_mutation=0.0,
        )
        by_role = {}
        for asset in generate_hazy_midi_essentials(recipe):
            by_role.setdefault(asset.role, {})[asset.variation] = asset.notes
        self.assertEqual(
            set(by_role), {"chords", "bass", "motif", "arpeggio", "drum_pattern"}
        )
        for role, variations in by_role.items():
            with self.subTest(role=role):
                self.assertEqual(variations["A"], variations["B"])
                self.assertEqual(variations["A"], variations["C"])

    def test_zero_groove_drift_keeps_motif_and_arpeggio_on_their_grids(self) -> None:
        assets = generate_hazy_midi_essentials(
            HazyMidiRecipe(
                seed=1842,
                groove_drift=0,
                motif_mutation=1.0,
                arpeggio_mutation=1.0,
            )
        )
        for asset in assets:
            if asset.role == "motif":
                with self.subTest(role=asset.role, variation=asset.variation):
                    self.assertTrue(all(note.start % PPQ == 0 for note in asset.notes))
            elif asset.role == "arpeggio":
                with self.subTest(role=asset.role, variation=asset.variation):
                    self.assertTrue(all(note.start % (PPQ // 2) == 0 for note in asset.notes))

    def test_zero_color_and_ambiguity_disable_their_chord_treatments(self) -> None:
        colorless = [
            asset
            for asset in generate_hazy_midi_essentials(
                HazyMidiRecipe(seed=1842, color_amount=0.0, chord_mutation=1.0)
            )
            if asset.role == "chords"
        ]
        self.assertFalse(
            {"add2", "add6", "7"}
            & {color for asset in colorless for color in asset.metadata["color_behavior"]}
        )

        unambiguous = [
            asset
            for asset in generate_hazy_midi_essentials(
                HazyMidiRecipe(seed=1842, ambiguity=0.0, chord_mutation=1.0)
            )
            if asset.role == "chords"
        ]
        self.assertFalse(
            {"sus2", "sus4", "open5"}
            & {color for asset in unambiguous for color in asset.metadata["color_behavior"]}
        )

        neutral = [
            asset
            for asset in generate_hazy_midi_essentials(
                HazyMidiRecipe(
                    seed=1842,
                    color_amount=0.0,
                    ambiguity=0.0,
                    chord_mutation=1.0,
                )
            )
            if asset.role == "chords"
        ]
        self.assertEqual(
            {color for asset in neutral for color in asset.metadata["color_behavior"]},
            {"triad"},
        )

    def test_pitch_duration_timing_velocity_and_drum_contracts_are_practical(self) -> None:
        clip_ticks = self.recipe.bars * BEATS_PER_BAR * PPQ
        for asset in self.assets:
            with self.subTest(role=asset.role, variation=asset.variation):
                self.assertTrue(all(0 <= note.start < note.end <= clip_ticks for note in asset.notes))
                self.assertTrue(all(45 <= note.velocity <= 105 for note in asset.notes))
                self.assertTrue(all(note.duration <= 4 * BEATS_PER_BAR * PPQ for note in asset.notes))
                if asset.note_range is not None:
                    low, high = asset.note_range
                    self.assertTrue(all(low <= note.note <= high for note in asset.notes))
                else:
                    self.assertEqual(dict(asset.drum_mapping), HAZY_GM_DRUM_MAPPING)
                    self.assertTrue(all(note.channel == 9 for note in asset.notes))
                    self.assertTrue(
                        all(note.note in HAZY_GM_DRUM_MAPPING.values() for note in asset.notes)
                    )

    def test_every_supported_mode_generates_without_expanding_druiid_scales(self) -> None:
        self.assertEqual(set(HAZY_MODES), {"major", "minor", "dorian", "mixolydian", "lydian", "aeolian"})
        for mode in HAZY_MODES:
            with self.subTest(mode=mode):
                assets = generate_hazy_midi_essentials(
                    HazyMidiRecipe(seed=12, root="F#", mode=mode, bars=1)
                )
                self.assertEqual(len(assets), 15)


class HazyPackTests(unittest.TestCase):
    def test_hazy_pack_midi_manifest_and_zip_are_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            recipe = HazyMidiRecipe(seed=1842)
            first = build_hazy_midi_pack(parent / "first", recipe)
            second = build_hazy_midi_pack(parent / "second", recipe)
            first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            second_manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(first_manifest, second_manifest)
            self.assertEqual(len(first_manifest["files"]), 15)
            self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())
            for item in first_manifest["files"]:
                self.assertEqual((first / item["path"]).read_bytes(), (second / item["path"]).read_bytes())
            self.assertEqual(first.with_suffix(".zip").read_bytes(), second.with_suffix(".zip").read_bytes())
            self.assertEqual(len(validate_pack(first)), 15)
            self.assertEqual(validate_zip(first.with_suffix(".zip"))["files"], 15)

    def test_undeclared_borrowed_note_fails_pack_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = build_hazy_midi_pack(Path(directory) / "pack", HazyMidiRecipe(seed=1842))
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            item = next(entry for entry in manifest["files"] if entry["metadata"]["borrowed_tones"])
            item["metadata"]["borrowed_tones"] = []
            write_manifest(manifest_path, manifest)
            with self.assertRaisesRegex(ValueError, "borrowed notes must be declared exactly"):
                validate_pack(root)

    def test_hazy_drum_channel_and_mapping_are_strictly_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = build_hazy_midi_pack(Path(directory) / "pack", HazyMidiRecipe(seed=55))
            manifest_path = root / "manifest.json"
            original = json.loads(manifest_path.read_text(encoding="utf-8"))
            drum_index = next(
                index for index, item in enumerate(original["files"]) if item["role"] == "drum_pattern"
            )
            wrong_channel = json.loads(json.dumps(original))
            wrong_channel["files"][drum_index]["metadata"]["channel"] = 9
            write_manifest(manifest_path, wrong_channel)
            with self.assertRaisesRegex(ValueError, "declared channel"):
                validate_pack(root)

            wrong_mapping = json.loads(json.dumps(original))
            wrong_mapping["files"][drum_index]["metadata"]["drum_mapping"]["open_hat"] = 44
            write_manifest(manifest_path, wrong_mapping)
            with self.assertRaisesRegex(ValueError, "drum mapping must match"):
                validate_pack(root)

    def test_every_hazy_file_carries_complete_identity_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = build_hazy_midi_pack(Path(directory) / "pack", HazyMidiRecipe(seed=6))
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["style"], "HAZY")
            self.assertEqual(manifest["format"]["midi_format"], 0)
            self.assertEqual(manifest["format"]["ppq"], 480)
            for item in manifest["files"]:
                metadata = item["metadata"]
                for field in (
                    "role",
                    "variation",
                    "scale",
                    "mode",
                    "degree_sequence",
                    "chord_symbols",
                    "voicing_or_color_behavior",
                    "borrowed_tones",
                    "timing_model",
                    "variation_relationship",
                ):
                    self.assertIn(field, metadata)
                self.assertTrue(item["path"].startswith("MIDI/HAZY_"))


if __name__ == "__main__":
    unittest.main()
