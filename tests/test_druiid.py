import unittest

from abletools.druiid import GM_DRUM_MAPPING, generate_midi_essentials
from abletools.recipe import ROOTS, MidiEssentialsRecipe, SCALES


class DruiidGeneratorTests(unittest.TestCase):
    def test_essentials_contains_related_abc_forms_for_every_role(self) -> None:
        assets = generate_midi_essentials(MidiEssentialsRecipe(seed=1842))
        self.assertEqual(len(assets), 12)
        by_role = {}
        for asset in assets:
            by_role.setdefault(asset.role, {})[asset.variation] = asset
        self.assertEqual(set(by_role), {"chords", "bass", "motif", "drum_pattern"})
        for role, variations in by_role.items():
            with self.subTest(role=role):
                self.assertEqual(set(variations), {"A", "B", "C"})
                self.assertNotEqual(variations["A"].notes, variations["B"].notes)
                self.assertNotEqual(variations["A"].notes, variations["C"].notes)

    def test_pitched_assets_are_scale_aware_and_in_practical_ranges(self) -> None:
        recipe = MidiEssentialsRecipe(seed=77, root="D", scale="minor")
        scale_pitch_classes = {(2 + interval) % 12 for interval in SCALES["minor"]}
        for asset in generate_midi_essentials(recipe):
            if asset.note_range is None:
                continue
            with self.subTest(role=asset.role, variation=asset.variation):
                low, high = asset.note_range
                self.assertTrue(all(low <= note.note <= high for note in asset.notes))
                self.assertTrue(all(note.note % 12 in scale_pitch_classes for note in asset.notes))

    def test_every_canonical_root_and_scale_generates(self) -> None:
        for root in ROOTS:
            for scale in SCALES:
                with self.subTest(root=root, scale=scale):
                    assets = generate_midi_essentials(
                        MidiEssentialsRecipe(seed=12, root=root, scale=scale, bars=1)
                    )
                    self.assertEqual(len(assets), 12)

    def test_chord_metadata_is_degree_first_and_symbolized(self) -> None:
        recipe = MidiEssentialsRecipe(seed=1, progression=(1, 6, 4, 5))
        chords = next(
            asset
            for asset in generate_midi_essentials(recipe)
            if asset.role == "chords" and asset.variation == "A"
        )
        self.assertEqual(chords.metadata["degree_sequence"], [1, 6, 4, 5])
        self.assertEqual(len(chords.metadata["chord_symbols"]), 4)
        self.assertEqual(chords.metadata["profile_version"], "DRUIID_R1")
        self.assertIsNone(chords.metadata["non_deterministic_stage"])

    def test_upper_mutation_does_not_change_bass_generation(self) -> None:
        first = MidiEssentialsRecipe(seed=812, upper_mutation=0.0, bass_mutation=0.75)
        second = MidiEssentialsRecipe(seed=812, upper_mutation=1.0, bass_mutation=0.75)
        first_bass = [asset.notes for asset in generate_midi_essentials(first) if asset.role == "bass"]
        second_bass = [asset.notes for asset in generate_midi_essentials(second) if asset.role == "bass"]
        self.assertEqual(first_bass, second_bass)

    def test_drums_use_declared_gm_mapping_on_channel_ten(self) -> None:
        drums = [
            asset
            for asset in generate_midi_essentials(MidiEssentialsRecipe(seed=9))
            if asset.role == "drum_pattern"
        ]
        for asset in drums:
            with self.subTest(variation=asset.variation):
                self.assertEqual(dict(asset.drum_mapping), GM_DRUM_MAPPING)
                self.assertTrue(all(note.channel == 9 for note in asset.notes))
                self.assertTrue(all(note.note in GM_DRUM_MAPPING.values() for note in asset.notes))


if __name__ == "__main__":
    unittest.main()
