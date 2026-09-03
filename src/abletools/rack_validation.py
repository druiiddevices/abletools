"""Strict semantic validation for Ableton rack blueprint build specifications."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .ableton_registry import DEVICE_REGISTRY, get_device, get_parameter
from .capabilities import get_capability
from .rack_blueprint import BLUEPRINT_NOTICE, BLUEPRINT_SCHEMA_VERSION, RACK_FAMILIES, VARIATIONS

TOP_LEVEL_FIELDS = {
    "schema_version", "blueprint_notice", "capability", "native_format", "rack_name", "family",
    "rack_type", "style", "version", "minimum_live_version", "seed", "dependencies",
    "intended_sources", "topology", "input_assumptions", "dry_strategy", "gain_staging",
    "behavior_notes", "macros", "macro_variations", "randomization_exclusions",
    "validation_declarations",
}
CHAIN_FIELDS = {"id", "name", "role", "level_db", "pan", "pass_through", "devices"}
DEVICE_FIELDS = {"id", "registry_id", "name", "stage", "enabled", "path", "settings"}
MACRO_FIELDS = {
    "index", "name", "color", "info_text", "default", "minimum", "maximum", "neutral_value",
    "polarity", "curve", "exclude_from_randomization", "zero_behavior", "targets",
}
TARGET_FIELDS = {"device_path", "parameter_id", "minimum", "maximum", "neutral", "direction", "purpose"}
FAMILY_TYPES = {
    "AGE_MACHINE": "audio_effect_rack",
    "RHYTHM_FRACTURE": "audio_effect_rack",
    "OPERATOR_SUB_FORM": "operator_instrument_rack",
    "OPERATOR_MEMORY_PAD": "operator_instrument_rack",
    "MIDI_PATTERN_MUTATOR": "midi_effect_rack",
}
NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")
ID = re.compile(r"^[a-z][a-z0-9_]*$")
COLOR = re.compile(r"^#[0-9A-F]{6}$")
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def _object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing = fields - value.keys()
    unknown = value.keys() - fields
    if missing:
        raise ValueError(f"{label} missing required fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(sorted(unknown))}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _unique_text_list(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f"{label} must be{' a non-empty' if nonempty else ' an'} array")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{label} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    return value


def _validate_device_settings(device: dict[str, Any]) -> None:
    definition = get_device(device["registry_id"])
    if device["name"] != definition.display_name:
        raise ValueError(f"device name disagrees with registry: {device['path']}")
    if device["stage"] != definition.stage:
        raise ValueError(f"device stage disagrees with registry: {device['path']}")
    settings = device["settings"]
    if not isinstance(settings, dict) or not settings:
        raise ValueError(f"device settings must be a non-empty object: {device['path']}")
    for parameter_id, value in settings.items():
        parameter = get_parameter(device["registry_id"], parameter_id)
        try:
            parameter.validate(value)
        except ValueError as error:
            raise ValueError(f"invalid setting {device['path']}:{parameter_id}: {error}") from error


def _validate_stage_order(rack_type: str, devices: list[dict[str, Any]]) -> None:
    stages = [device["stage"] for device in devices]
    if rack_type == "audio_effect_rack":
        if any(stage != "audio_effect" for stage in stages):
            raise ValueError("audio racks may contain only audio-effect devices")
    elif rack_type == "midi_effect_rack":
        if not devices or any(stage != "midi_effect" for stage in stages):
            raise ValueError("MIDI racks may contain only MIDI-effect devices")
    else:
        if stages.count("instrument") != 1:
            raise ValueError("Operator instrument racks require exactly one instrument")
        instrument_index = stages.index("instrument")
        if any(stage != "midi_effect" for stage in stages[:instrument_index]) or any(
            stage != "audio_effect" for stage in stages[instrument_index + 1:]
        ):
            raise ValueError("instrument topology must order MIDI effects, instrument, then audio effects")


def _validate_macro(
    macro: dict[str, Any], device_by_path: dict[str, dict[str, Any]], exclusions: set[str]
) -> None:
    _object(macro, MACRO_FIELDS, "macro")
    if isinstance(macro["index"], bool) or not isinstance(macro["index"], int):
        raise ValueError("macro index must be an integer")
    if not isinstance(macro["name"], str) or not NAME.fullmatch(macro["name"]):
        raise ValueError("macro name must use canonical uppercase identifiers")
    if not isinstance(macro["color"], str) or not COLOR.fullmatch(macro["color"]):
        raise ValueError("macro color must be uppercase six-digit hexadecimal")
    _text(macro["info_text"], "macro info_text")
    _text(macro["zero_behavior"], "macro zero_behavior")
    minimum = _number(macro["minimum"], "macro minimum")
    maximum = _number(macro["maximum"], "macro maximum")
    default = _number(macro["default"], "macro default")
    neutral = _number(macro["neutral_value"], "macro neutral_value")
    if not (0 <= minimum < maximum <= 127 and minimum <= default <= maximum and minimum <= neutral <= maximum):
        raise ValueError("macro range, default, and neutral must be bounded from 0 to 127")
    if macro["polarity"] not in {"unipolar", "bipolar"} or macro["curve"] not in {
        "linear", "logarithmic", "exponential"
    }:
        raise ValueError("macro polarity or curve is unknown")
    if not isinstance(macro["exclude_from_randomization"], bool):
        raise ValueError("macro randomization exclusion must be boolean")
    if macro["exclude_from_randomization"] and f"macro:{macro['name']}" not in exclusions:
        raise ValueError(f"excluded macro missing randomization declaration: {macro['name']}")
    targets = macro["targets"]
    if not isinstance(targets, list) or not targets:
        raise ValueError(f"macro requires at least one target: {macro['name']}")
    seen: set[tuple[str, str]] = set()
    for target in targets:
        _object(target, TARGET_FIELDS, f"macro target {macro['name']}")
        path = _text(target["device_path"], "macro target path")
        parameter_id = _text(target["parameter_id"], "macro target parameter")
        if path not in device_by_path:
            raise ValueError(f"macro target references unknown device path: {path}")
        key = (path, parameter_id)
        if key in seen:
            raise ValueError(f"macro contains duplicate target: {path}:{parameter_id}")
        seen.add(key)
        device = device_by_path[path]
        parameter = get_parameter(device["registry_id"], parameter_id)
        if parameter.kind not in {"number", "integer"}:
            raise ValueError(f"macro target must be a numeric documented parameter: {path}:{parameter_id}")
        target_minimum = _number(target["minimum"], "target minimum")
        target_maximum = _number(target["maximum"], "target maximum")
        target_neutral = _number(target["neutral"], "target neutral")
        if target_minimum > target_maximum or not target_minimum <= target_neutral <= target_maximum:
            raise ValueError(f"macro target has malformed range: {path}:{parameter_id}")
        try:
            parameter.validate(target["minimum"])
            parameter.validate(target["maximum"])
            parameter.validate(target["neutral"])
        except ValueError as error:
            raise ValueError(f"macro target exceeds safe registry range: {path}:{parameter_id}") from error
        if target["direction"] not in {"direct", "inverse"}:
            raise ValueError("macro target direction is unknown")
        _text(target["purpose"], "macro target purpose")


def validate_rack_blueprint(data: dict[str, Any]) -> dict[str, Any]:
    """Validate syntax, registry membership, routing, mappings, and safety declarations."""
    data = _object(data, TOP_LEVEL_FIELDS, "rack blueprint")
    if data["schema_version"] != BLUEPRINT_SCHEMA_VERSION:
        raise ValueError(f"rack blueprint schema_version must be {BLUEPRINT_SCHEMA_VERSION}")
    if data["blueprint_notice"] != BLUEPRINT_NOTICE or data["native_format"] is not False:
        raise ValueError("blueprint must prominently declare that it is not a native Ableton file")
    if data["capability"] != "ableton_rack_blueprint" or not get_capability(data["capability"]).enabled:
        raise ValueError("rack blueprint capability is unknown or disabled")
    if not isinstance(data["rack_name"], str) or not NAME.fullmatch(data["rack_name"]):
        raise ValueError("rack_name must be a canonical uppercase identifier")
    if data["family"] not in RACK_FAMILIES:
        raise ValueError("unknown rack family")
    if data["rack_type"] != FAMILY_TYPES[data["family"]]:
        raise ValueError("rack family and rack type disagree")
    if data["style"] not in {"DRUIID", "HAZY"} or not data["rack_name"].startswith(data["style"] + "_"):
        raise ValueError("rack style and name disagree")
    if not isinstance(data["version"], str) or not SEMVER.fullmatch(data["version"]):
        raise ValueError("rack version must be semantic version text")
    if data["minimum_live_version"] != "12.0":
        raise ValueError("Milestone 3A blueprints require Ableton Live 12.0 or newer")
    if isinstance(data["seed"], bool) or not isinstance(data["seed"], int) or data["seed"] < 0:
        raise ValueError("rack seed must be a non-negative integer")
    dependencies = _unique_text_list(data["dependencies"], "dependencies")
    _unique_text_list(data["intended_sources"], "intended_sources", nonempty=True)

    topology = _object(data["topology"], {"chains"}, "topology")
    if not isinstance(topology["chains"], list) or not topology["chains"]:
        raise ValueError("topology requires at least one chain")
    chain_ids: set[str] = set()
    device_by_path: dict[str, dict[str, Any]] = {}
    all_devices: list[dict[str, Any]] = []
    for chain in topology["chains"]:
        _object(chain, CHAIN_FIELDS, "chain")
        if not isinstance(chain["id"], str) or not ID.fullmatch(chain["id"]):
            raise ValueError("chain id must be canonical lowercase text")
        if chain["id"] in chain_ids:
            raise ValueError(f"duplicate chain id: {chain['id']}")
        chain_ids.add(chain["id"])
        _text(chain["name"], "chain name")
        _text(chain["role"], "chain role")
        if not -60 <= _number(chain["level_db"], "chain level") <= 12:
            raise ValueError("chain level is outside the supported range")
        if not -1 <= _number(chain["pan"], "chain pan") <= 1:
            raise ValueError("chain pan is outside the supported range")
        if not isinstance(chain["pass_through"], bool) or not isinstance(chain["devices"], list):
            raise ValueError("chain pass_through or devices is malformed")
        if chain["pass_through"] and chain["devices"]:
            raise ValueError("a pass-through chain cannot contain devices")
        device_ids: set[str] = set()
        for device in chain["devices"]:
            _object(device, DEVICE_FIELDS, "device")
            if not isinstance(device["id"], str) or not ID.fullmatch(device["id"]):
                raise ValueError("device id must be canonical lowercase text")
            if device["id"] in device_ids:
                raise ValueError(f"duplicate device id in chain: {device['id']}")
            device_ids.add(device["id"])
            expected_path = f"chains/{chain['id']}/devices/{device['id']}"
            if device["path"] != expected_path or device["path"] in device_by_path:
                raise ValueError(f"device path is noncanonical or duplicated: {device['path']}")
            if not isinstance(device["enabled"], bool):
                raise ValueError("device enabled flag must be boolean")
            _validate_device_settings(device)
            device_by_path[device["path"]] = device
            all_devices.append(device)
        _validate_stage_order(data["rack_type"], chain["devices"])
    if dependencies != sorted({device["name"] for device in all_devices}):
        raise ValueError("dependencies must exactly match the stock-device inventory")

    input_assumptions = _object(
        data["input_assumptions"],
        {"signal_type", "description", "incoming_note_behavior", "outgoing_note_behavior"},
        "input_assumptions",
    )
    expected_signal = "audio" if data["rack_type"] == "audio_effect_rack" else "midi"
    if input_assumptions["signal_type"] != expected_signal:
        raise ValueError("input signal type disagrees with rack type")
    for field in ("description", "incoming_note_behavior", "outgoing_note_behavior"):
        _text(input_assumptions[field], f"input_assumptions {field}")
    dry = _object(data["dry_strategy"], {"mode", "details"}, "dry_strategy")
    _text(dry["details"], "dry strategy details")
    if data["rack_type"] == "audio_effect_rack":
        if dry["mode"] not in {"serial_mix", "parallel_dry_chain"}:
            raise ValueError("audio racks require an explicit dry strategy")
        if dry["mode"] == "parallel_dry_chain" and not any(chain["pass_through"] for chain in topology["chains"]):
            raise ValueError("parallel dry strategy requires a pass-through chain")
    elif dry["mode"] != "not_applicable":
        raise ValueError("MIDI and instrument racks must not claim an audio dry path")

    gain = _object(
        data["gain_staging"], {"input_headroom_db", "output_ceiling_db", "output_trim_macro", "details"}, "gain_staging"
    )
    _text(gain["details"], "gain staging details")
    if data["rack_type"] == "midi_effect_rack":
        if any(gain[field] is not None for field in ("input_headroom_db", "output_ceiling_db", "output_trim_macro")):
            raise ValueError("MIDI-only racks cannot declare audio gain or output trim")
    else:
        if gain["output_trim_macro"] != "OUT" or not isinstance(gain["input_headroom_db"], (int, float)) or not isinstance(gain["output_ceiling_db"], (int, float)):
            raise ValueError("audio and instrument racks require explicit OUT trim and gain limits")
    behavior = _object(data["behavior_notes"], {"latency", "tail", "mono", "stereo", "low_frequency", "bypass"}, "behavior_notes")
    for field, value in behavior.items():
        _text(value, f"behavior note {field}")
    if data["rack_type"] == "midi_effect_rack" and (
        not behavior["tail"].startswith("not_applicable")
        or not behavior["stereo"].startswith("not_applicable")
    ):
        raise ValueError("MIDI-only racks must not claim audio tail or stereo behavior")

    exclusions = set(_unique_text_list(data["randomization_exclusions"], "randomization_exclusions"))
    macros = data["macros"]
    expected_macro_count = 16 if data["rack_type"] == "operator_instrument_rack" else 12
    if not isinstance(macros, list) or len(macros) != expected_macro_count:
        raise ValueError(f"rack requires exactly {expected_macro_count} macros")
    for macro in macros:
        _validate_macro(macro, device_by_path, exclusions)
    indices = [macro["index"] for macro in macros]
    names = [macro["name"] for macro in macros]
    if indices != list(range(1, expected_macro_count + 1)):
        raise ValueError("macro indices must be unique, contiguous, and 1-based")
    if len(names) != len(set(names)):
        raise ValueError("macro names must be unique")
    multi_target_count = sum(len(macro["targets"]) >= 2 for macro in macros)
    required_multi = 6 if data["rack_type"] == "operator_instrument_rack" else 4
    if multi_target_count < required_multi:
        raise ValueError(f"rack requires at least {required_multi} multi-target macros")

    if data["rack_type"] == "midi_effect_rack":
        if "OUT" in names or any(device["stage"] != "midi_effect" for device in all_devices):
            raise ValueError("MIDI rack cannot contain audio concepts or stages")
    else:
        if names.count("OUT") != 1:
            raise ValueError("audio and instrument racks require exactly one OUT macro")
        output = macros[names.index("OUT")]
        if not output["exclude_from_randomization"] or not any(
            device_by_path[target["device_path"]]["registry_id"] == "utility"
            and target["parameter_id"] == "gain_db"
            for target in output["targets"]
        ):
            raise ValueError("OUT must be excluded and target a real Utility gain control")

    if data["rack_type"] == "operator_instrument_rack":
        operator = next((device for device in all_devices if device["registry_id"] == "operator"), None)
        if operator is None:
            raise ValueError("Operator instrument rack requires Operator")
        if set(operator["settings"]) != set(DEVICE_REGISTRY["operator"].parameters):
            raise ValueError("Operator specification must declare every required synthesis setting")
        if not any(
            {device_by_path[target["device_path"]]["stage"] for target in macro["targets"]}
            >= {"instrument", "audio_effect"}
            for macro in macros
        ):
            raise ValueError("Operator rack requires a macro spanning synthesis and downstream effects")

    for device in all_devices:
        definition = get_device(device["registry_id"])
        for parameter_id in device["settings"]:
            if definition.parameters[parameter_id].safety_critical:
                token = f"parameter:{device['path']}:{parameter_id}"
                if token not in exclusions:
                    raise ValueError(f"safety-critical parameter missing randomization exclusion: {token}")

    variations = data["macro_variations"]
    if not isinstance(variations, dict) or set(variations) != set(VARIATIONS):
        raise ValueError("macro variations must be INIT, SUBTLE, ACTIVE, and EXTREME_SAFE")
    macro_by_name = {macro["name"]: macro for macro in macros}
    for variation_name in VARIATIONS:
        values = variations[variation_name]
        if not isinstance(values, dict) or set(values) != set(names):
            raise ValueError(f"variation must cover every macro exactly once: {variation_name}")
        for name, value in values.items():
            macro = macro_by_name[name]
            numeric = _number(value, f"variation {variation_name} macro {name}")
            if not macro["minimum"] <= numeric <= macro["maximum"]:
                raise ValueError(f"variation value is outside macro range: {variation_name}:{name}")
            if variation_name == "INIT" and numeric != macro["neutral_value"]:
                raise ValueError(f"INIT must use the declared neutral value: {name}")
            if macro["exclude_from_randomization"] and numeric != macro["default"]:
                raise ValueError(f"safety/output macro must remain stable across variations: {name}")

    declarations = _object(
        data["validation_declarations"],
        {"schema", "registry", "structural", "ableton_open", "listening_test", "native_export_gate"},
        "validation_declarations",
    )
    expected_declarations = {
        "schema": "required", "registry": "required", "structural": "required",
        "ableton_open": "not_performed_native_export_gated",
        "listening_test": "not_performed_native_export_gated", "native_export_gate": "closed",
    }
    if declarations != expected_declarations:
        raise ValueError("validation declarations must preserve the native-format gate")
    return {
        "blueprint": data["rack_name"],
        "devices": len(all_devices),
        "family": data["family"],
        "macros": len(macros),
        "native_format": False,
        "rack_type": data["rack_type"],
        "result": "valid",
        "schema_version": data["schema_version"],
        "seed": data["seed"],
        "style": data["style"],
    }


def validate_rack_blueprint_file(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("rack blueprint must be valid UTF-8 JSON") from error
    return validate_rack_blueprint(data)
