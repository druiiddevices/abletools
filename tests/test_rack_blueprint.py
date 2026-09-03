import copy
import json
import tempfile
import unittest
from pathlib import Path

from abletools.ableton_registry import get_device, get_parameter
from abletools.pack import validate_pack, validate_zip
from abletools.rack_blueprint import (
    BLUEPRINT_NOTICE,
    RACK_FAMILIES,
    RackBlueprintRecipe,
    generate_rack_blueprints,
)
from abletools.rack_pack import build_rack_blueprint_pack
from abletools.rack_validation import validate_rack_blueprint


class RackBlueprintTests(unittest.TestCase):
    @staticmethod
    def _catalog(style: str = "DRUIID") -> list[dict[str, object]]:
        return generate_rack_blueprints(RackBlueprintRecipe(seed=1842, style=style))

    @staticmethod
    def _family(catalog: list[dict[str, object]], family: str) -> dict[str, object]:
        return next(item for item in catalog if item["family"] == family)

    def test_catalog_is_exact_and_every_blueprint_validates(self) -> None:
        for style in ("DRUIID", "HAZY"):
            with self.subTest(style=style):
                catalog = self._catalog(style)
                self.assertEqual(tuple(item["family"] for item in catalog), RACK_FAMILIES)
                self.assertEqual(len(catalog), 5)
                for blueprint in catalog:
                    result = validate_rack_blueprint(blueprint)
                    self.assertEqual(result["result"], "valid")
                    self.assertFalse(result["native_format"])
                    self.assertEqual(blueprint["blueprint_notice"], BLUEPRINT_NOTICE)

    def test_pack_manifest_blueprints_and_zip_are_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            for style in ("DRUIID", "HAZY"):
                with self.subTest(style=style):
                    recipe = RackBlueprintRecipe(seed=1842, style=style)
                    first = build_rack_blueprint_pack(parent / f"{style}-first", recipe)
                    second = build_rack_blueprint_pack(parent / f"{style}-second", recipe)
                    first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
                    second_manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
                    self.assertEqual(first_manifest, second_manifest)
                    self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())
                    for item in first_manifest["files"]:
                        self.assertEqual((first / item["path"]).read_bytes(), (second / item["path"]).read_bytes())
                    self.assertEqual(first.with_suffix(".zip").read_bytes(), second.with_suffix(".zip").read_bytes())
                    self.assertEqual(len(validate_pack(first)), 5)
                    self.assertEqual(validate_zip(first.with_suffix(".zip"))["files"], 5)

    def test_macro_counts_names_indices_and_targets_are_complete(self) -> None:
        for blueprint in self._catalog() + self._catalog("HAZY"):
            expected = 16 if blueprint["rack_type"] == "operator_instrument_rack" else 12
            macros = blueprint["macros"]
            self.assertEqual(len(macros), expected)
            self.assertEqual([item["index"] for item in macros], list(range(1, expected + 1)))
            self.assertEqual(len({item["name"] for item in macros}), expected)
            self.assertTrue(all(item["info_text"] and item["color"] and item["targets"] for item in macros))

    def test_registry_resolves_every_device_setting_and_macro_target(self) -> None:
        for blueprint in self._catalog() + self._catalog("HAZY"):
            devices = {
                device["path"]: device
                for chain in blueprint["topology"]["chains"]
                for device in chain["devices"]
            }
            for device in devices.values():
                definition = get_device(device["registry_id"])
                for parameter_id, value in device["settings"].items():
                    definition.parameters[parameter_id].validate(value)
            for macro in blueprint["macros"]:
                for target in macro["targets"]:
                    device = devices[target["device_path"]]
                    parameter = get_parameter(device["registry_id"], target["parameter_id"])
                    parameter.validate(target["minimum"])
                    parameter.validate(target["maximum"])
                    parameter.validate(target["neutral"])

    def test_multi_target_output_and_safety_contracts(self) -> None:
        for blueprint in self._catalog() + self._catalog("HAZY"):
            required = 6 if blueprint["rack_type"] == "operator_instrument_rack" else 4
            self.assertGreaterEqual(sum(len(item["targets"]) >= 2 for item in blueprint["macros"]), required)
            if blueprint["rack_type"] == "midi_effect_rack":
                self.assertNotIn("OUT", {item["name"] for item in blueprint["macros"]})
                self.assertIsNone(blueprint["gain_staging"]["output_trim_macro"])
            else:
                out = next(item for item in blueprint["macros"] if item["name"] == "OUT")
                self.assertTrue(out["exclude_from_randomization"])
                self.assertIn("macro:OUT", blueprint["randomization_exclusions"])
                self.assertEqual(blueprint["gain_staging"]["output_trim_macro"], "OUT")

    def test_variations_cover_all_macros_and_hold_safety_stable(self) -> None:
        for blueprint in self._catalog() + self._catalog("HAZY"):
            names = {macro["name"] for macro in blueprint["macros"]}
            self.assertEqual(set(blueprint["macro_variations"]), {"INIT", "SUBTLE", "ACTIVE", "EXTREME_SAFE"})
            for variation in blueprint["macro_variations"].values():
                self.assertEqual(set(variation), names)
            for macro in blueprint["macros"]:
                self.assertEqual(blueprint["macro_variations"]["INIT"][macro["name"]], macro["neutral_value"])
                if macro["exclude_from_randomization"]:
                    self.assertEqual(
                        {variation[macro["name"]] for variation in blueprint["macro_variations"].values()},
                        {macro["default"]},
                    )

    def test_operator_specs_are_complete_and_include_cross_stage_morph(self) -> None:
        for style in ("DRUIID", "HAZY"):
            for family in ("OPERATOR_SUB_FORM", "OPERATOR_MEMORY_PAD"):
                blueprint = self._family(self._catalog(style), family)
                devices = [device for chain in blueprint["topology"]["chains"] for device in chain["devices"]]
                operator = next(device for device in devices if device["registry_id"] == "operator")
                self.assertEqual(set(operator["settings"]), set(get_device("operator").parameters))
                paths = {device["path"]: device["stage"] for device in devices}
                self.assertTrue(
                    any({paths[target["device_path"]] for target in macro["targets"]} >= {"instrument", "audio_effect"} for macro in blueprint["macros"])
                )

    def test_audio_racks_declare_dry_strategy_and_gain_staging(self) -> None:
        for style in ("DRUIID", "HAZY"):
            for family in ("AGE_MACHINE", "RHYTHM_FRACTURE"):
                blueprint = self._family(self._catalog(style), family)
                self.assertIn(blueprint["dry_strategy"]["mode"], {"serial_mix", "parallel_dry_chain"})
                self.assertEqual(blueprint["gain_staging"]["output_trim_macro"], "OUT")
                self.assertLessEqual(blueprint["gain_staging"]["output_ceiling_db"], -1.0)

    def test_midi_mutator_is_midi_only_and_has_explicit_note_contract(self) -> None:
        for style in ("DRUIID", "HAZY"):
            blueprint = self._family(self._catalog(style), "MIDI_PATTERN_MUTATOR")
            devices = [device for chain in blueprint["topology"]["chains"] for device in chain["devices"]]
            self.assertTrue(all(device["stage"] == "midi_effect" for device in devices))
            self.assertEqual(blueprint["dry_strategy"]["mode"], "not_applicable")
            self.assertIn("note_off", blueprint["input_assumptions"]["outgoing_note_behavior"])

            malformed = copy.deepcopy(blueprint)
            malformed["topology"]["chains"][0]["devices"][0]["stage"] = "audio_effect"
            with self.assertRaisesRegex(ValueError, "stage disagrees|MIDI racks"):
                validate_rack_blueprint(malformed)

    def test_paired_styles_are_structurally_and_semantically_distinct(self) -> None:
        druiid = {item["family"]: item for item in self._catalog("DRUIID")}
        hazy = {item["family"]: item for item in self._catalog("HAZY")}
        for family in RACK_FAMILIES:
            with self.subTest(family=family):
                left = copy.deepcopy(druiid[family])
                right = copy.deepcopy(hazy[family])
                for item in (left, right):
                    item.pop("rack_name")
                    item.pop("style")
                self.assertNotEqual(left["topology"], right["topology"])
                self.assertNotEqual(left["macros"], right["macros"])

    def test_neutral_state_is_explicit_and_does_not_force_nonzero_values(self) -> None:
        for blueprint in self._catalog() + self._catalog("HAZY"):
            for macro in blueprint["macros"]:
                self.assertIn("neutral", macro["zero_behavior"].lower())
                self.assertEqual(blueprint["macro_variations"]["INIT"][macro["name"]], macro["neutral_value"])

    def test_unknown_device_parameter_path_and_capability_fail_closed(self) -> None:
        base = self._catalog()[0]
        mutations = []
        unknown_device = copy.deepcopy(base)
        unknown_device["topology"]["chains"][0]["devices"][0]["registry_id"] = "imaginary_device"
        mutations.append((unknown_device, "unknown Ableton stock device"))
        unknown_parameter = copy.deepcopy(base)
        unknown_parameter["topology"]["chains"][0]["devices"][0]["settings"]["imaginary"] = 1
        mutations.append((unknown_parameter, "unknown parameter"))
        unknown_path = copy.deepcopy(base)
        unknown_path["macros"][0]["targets"][0]["device_path"] = "chains/nope/devices/nope"
        mutations.append((unknown_path, "unknown device path"))
        unknown_capability = copy.deepcopy(base)
        unknown_capability["capability"] = "ableton_rack"
        mutations.append((unknown_capability, "unknown or disabled"))
        for blueprint, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex((ValueError, RuntimeError), message):
                validate_rack_blueprint(blueprint)

    def test_unsafe_ranges_and_missing_safety_exclusions_fail(self) -> None:
        base = self._catalog()[0]
        unsafe = copy.deepcopy(base)
        unsafe["macros"][0]["targets"][0]["maximum"] = 999999
        with self.assertRaisesRegex(ValueError, "safe registry range"):
            validate_rack_blueprint(unsafe)
        missing = copy.deepcopy(base)
        token = next(item for item in missing["randomization_exclusions"] if item.startswith("parameter:"))
        missing["randomization_exclusions"].remove(token)
        with self.assertRaisesRegex(ValueError, "safety-critical parameter"):
            validate_rack_blueprint(missing)

    def test_missing_duplicate_and_malformed_macros_fail(self) -> None:
        base = self._catalog()[0]
        missing = copy.deepcopy(base)
        missing["macros"].pop()
        with self.assertRaisesRegex(ValueError, "exactly 12 macros"):
            validate_rack_blueprint(missing)
        duplicate = copy.deepcopy(base)
        duplicate["macros"][1]["name"] = duplicate["macros"][0]["name"]
        with self.assertRaisesRegex(ValueError, "macro names must be unique"):
            validate_rack_blueprint(duplicate)
        malformed = copy.deepcopy(base)
        malformed["macros"][0]["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            validate_rack_blueprint(malformed)

    def test_schema_is_strict_json_schema_2020_12(self) -> None:
        schema = json.loads((Path(__file__).parents[1] / "schemas" / "rack-blueprint.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["native_format"], {"const": False})


if __name__ == "__main__":
    unittest.main()
