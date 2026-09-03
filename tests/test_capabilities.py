import unittest

from abletools.capabilities import get_capability, require_capability
from abletools.recipe import HazyMidiRecipe, MidiEssentialsRecipe, route_profile


class CapabilityTests(unittest.TestCase):
    def test_enabled_runtime_capabilities_are_explicit(self) -> None:
        self.assertTrue(require_capability("standard_midi").enabled)
        self.assertTrue(require_capability("zip_pack").enabled)
        self.assertTrue(require_capability("druiid_midi_essentials").enabled)
        self.assertTrue(require_capability("hazy_midi_essentials").enabled)

    def test_native_exporters_remain_gated(self) -> None:
        for name in ("serum2_preset", "ableton_rack", "ableton_groove", "max_for_live"):
            with self.subTest(name=name):
                self.assertEqual(get_capability(name).status, "gated")
                with self.assertRaisesRegex(RuntimeError, "fixture-based round-trip tests"):
                    require_capability(name)

    def test_hazy_profile_routes_to_its_separate_implemented_profile(self) -> None:
        self.assertEqual(route_profile("HAZY"), "HAZY_R1")
        self.assertEqual(HazyMidiRecipe(seed=1842).profile_version, "HAZY_R1")

    def test_recipe_is_canonical_and_role_controls_are_isolated(self) -> None:
        first = MidiEssentialsRecipe(seed=1842, upper_mutation=0.25, bass_mutation=0.75)
        second = MidiEssentialsRecipe(seed=1842, upper_mutation=0.25, bass_mutation=0.75)
        changed_upper = MidiEssentialsRecipe(seed=1842, upper_mutation=1.0, bass_mutation=0.75)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.role_seed_data("bass"), changed_upper.role_seed_data("bass"))
        self.assertNotEqual(first.role_seed_data("chords"), changed_upper.role_seed_data("chords"))

    def test_recipe_rejects_noncanonical_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "root must"):
            MidiEssentialsRecipe(seed=1, root="Db")
        with self.assertRaisesRegex(ValueError, "seed must"):
            MidiEssentialsRecipe(seed=-1)


if __name__ == "__main__":
    unittest.main()
