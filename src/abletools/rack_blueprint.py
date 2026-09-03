"""Deterministic Ableton rack build specifications (never native rack files)."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .ableton_registry import get_device
from .capabilities import require_capability

BLUEPRINT_SCHEMA_VERSION = "1.0.0"
BLUEPRINT_NOTICE = "VALIDATED BUILD SPECIFICATION — NOT AN ABLETON .ADG/.ADV/.AGR/.AMXD FILE"
RACK_FAMILIES = (
    "AGE_MACHINE",
    "RHYTHM_FRACTURE",
    "OPERATOR_SUB_FORM",
    "OPERATOR_MEMORY_PAD",
    "MIDI_PATTERN_MUTATOR",
)
VARIATIONS = ("INIT", "SUBTLE", "ACTIVE", "EXTREME_SAFE")
STYLE_COLORS = {"DRUIID": "#7ED957", "HAZY": "#E2B7FF"}


@dataclass(frozen=True)
class RackBlueprintRecipe:
    seed: int = 1842
    style: str = "DRUIID"
    minimum_live_version: str = "12.0"

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if self.style not in {"DRUIID", "HAZY"}:
            raise ValueError("style must be DRUIID or HAZY")
        if self.minimum_live_version != "12.0":
            raise ValueError("Milestone 3A blueprints require minimum Live version 12.0")

    def canonical_data(self) -> dict[str, Any]:
        return {
            "minimum_live_version": self.minimum_live_version,
            "seed": self.seed,
            "style": self.style,
        }


@dataclass(frozen=True)
class RackBlueprint:
    """Validated immutable canonical representation of one blueprint."""

    canonical_json: str

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "RackBlueprint":
        from .rack_validation import validate_rack_blueprint

        validate_rack_blueprint(data)
        return cls(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True))

    def to_data(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


def _rng(recipe: RackBlueprintRecipe, family: str) -> random.Random:
    material = json.dumps(
        {"recipe": recipe.canonical_data(), "family": family}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return random.Random(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))


def _device(chain_id: str, identifier: str, instance_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    definition = get_device(identifier)
    return {
        "id": instance_id,
        "registry_id": identifier,
        "name": definition.display_name,
        "stage": definition.stage,
        "enabled": True,
        "path": f"chains/{chain_id}/devices/{instance_id}",
        "settings": settings,
    }


def _chain(
    chain_id: str,
    name: str,
    role: str,
    devices: list[dict[str, Any]],
    *,
    level_db: float = 0.0,
    pass_through: bool = False,
) -> dict[str, Any]:
    return {
        "id": chain_id,
        "name": name,
        "role": role,
        "level_db": level_db,
        "pan": 0.0,
        "pass_through": pass_through,
        "devices": devices,
    }


def _target(
    device_path: str,
    parameter_id: str,
    minimum: float,
    maximum: float,
    neutral: float,
    purpose: str,
    *,
    inverse: bool = False,
) -> dict[str, Any]:
    return {
        "device_path": device_path,
        "parameter_id": parameter_id,
        "minimum": minimum,
        "maximum": maximum,
        "neutral": neutral,
        "direction": "inverse" if inverse else "direct",
        "purpose": purpose,
    }


def _macro(
    index: int,
    name: str,
    targets: list[dict[str, Any]],
    style: str,
    *,
    bipolar: bool = False,
    output: bool = False,
) -> dict[str, Any]:
    neutral = 64.0 if bipolar or output else 0.0
    return {
        "index": index,
        "name": name,
        "color": STYLE_COLORS[style],
        "info_text": f"Safe, documented {name.replace('_', ' ').lower()} control for this build specification.",
        "default": neutral,
        "minimum": 0.0,
        "maximum": 127.0,
        "neutral_value": neutral,
        "polarity": "bipolar" if bipolar else "unipolar",
        "curve": "linear",
        "exclude_from_randomization": output,
        "zero_behavior": (
            "Center is the neutral unity output trim and remains stable across variations."
            if output
            else "Zero or the declared center is a deliberate neutral state; no hidden nonzero floor is applied."
        ),
        "targets": targets,
    }


def _variations(macros: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    levels = {"INIT": 0.0, "SUBTLE": 28.0, "ACTIVE": 68.0, "EXTREME_SAFE": 108.0}
    for variation, level in levels.items():
        values: dict[str, float] = {}
        for macro in macros:
            if macro["exclude_from_randomization"]:
                values[macro["name"]] = macro["default"]
            elif macro["polarity"] == "bipolar":
                values[macro["name"]] = 64.0 if variation == "INIT" else min(127.0, 64.0 + level * 0.42)
            else:
                values[macro["name"]] = macro["neutral_value"] if variation == "INIT" else level
        result[variation] = values
    return result


def _operator_settings(style: str, family: str, rng: random.Random) -> dict[str, Any]:
    pad = family == "OPERATOR_MEMORY_PAD"
    hazy = style == "HAZY"
    levels = (-5.0, -18.0 if not pad else -13.0, -60.0 if not hazy else -25.0, -60.0 if not pad else -31.0)
    ratios = ((1, 1), (2, 3), (1, 5), (4, 7)) if hazy else ((1, 1), (2, 0), (1, 0), (3, 0))
    waveforms = ("sine", "triangle", "sine", "noise_looped") if pad else ("sine", "sine", "triangle", "sine")
    settings: dict[str, Any] = {"algorithm": 7 if pad and hazy else 5 if pad else 2 if hazy else 1}
    for index, osc in enumerate("abcd"):
        attack = (650.0 + index * 180.0) if pad else (2.0 + index)
        release = (3200.0 + index * 500.0) if pad else (260.0 + index * 80.0)
        settings.update(
            {
                f"oscillator_{osc}_waveform": waveforms[index],
                f"oscillator_{osc}_level_db": levels[index],
                f"oscillator_{osc}_coarse": ratios[index][0],
                f"oscillator_{osc}_fine": ratios[index][1],
                f"oscillator_{osc}_fixed": bool(pad and hazy and osc == "d"),
                f"oscillator_{osc}_fixed_frequency_hz": 73.0 if pad and hazy and osc == "d" else 440.0,
                f"oscillator_{osc}_attack_ms": attack,
                f"oscillator_{osc}_decay_ms": 2400.0 if pad else 420.0,
                f"oscillator_{osc}_sustain_percent": 72.0 if pad else 80.0,
                f"oscillator_{osc}_release_ms": release,
            }
        )
    settings.update(
        {
            "filter_type": "low_pass_24" if not hazy else "low_pass_12",
            "filter_frequency_hz": round((420.0 if not pad else 2400.0) + rng.random() * 80.0, 3),
            "filter_resonance_percent": 18.0 if not hazy else 31.0,
            "filter_envelope_percent": 42.0 if not pad else 18.0,
            "filter_drive_db": 2.0 if not hazy else 1.0,
            "filter_key_tracking_percent": 72.0 if not pad else 48.0,
            "filter_velocity_percent": 22.0 if not pad else 35.0,
            "filter_attack_ms": 4.0 if not pad else 720.0,
            "filter_decay_ms": 780.0 if not pad else 4300.0,
            "filter_sustain_percent": 35.0 if not pad else 62.0,
            "filter_release_ms": 280.0 if not pad else 3800.0,
            "lfo_waveform": "triangle" if not hazy else "sample_hold",
            "lfo_rate_hz": 0.18 if pad else 2.4,
            "lfo_amount_percent": 8.0 if pad else 0.0,
            "lfo_destination": "filter" if pad else "oscillator_pitch",
            "lfo_sync": False,
            "lfo_retrigger": not (pad and hazy),
            "pitch_envelope_amount_st": 0.0 if pad else 7.0,
            "pitch_envelope_attack_ms": 0.0,
            "pitch_envelope_decay_ms": 95.0 if not pad else 600.0,
            "pitch_envelope_release_ms": 120.0 if not pad else 1400.0,
            "transpose_semitones": -12 if not pad else 0,
            "glide_ms": 36.0 if not pad else 0.0,
            "spread_percent": 0.0 if not pad else 28.0 if hazy else 18.0,
            "voices": 1 if not pad else 8,
            "velocity_to_volume_percent": 24.0 if not pad else 38.0,
            "master_volume_db": -12.0,
        }
    )
    return settings


def _base_blueprint(
    recipe: RackBlueprintRecipe,
    family: str,
    rack_type: str,
    chains: list[dict[str, Any]],
    macros: list[dict[str, Any]],
    *,
    intended_sources: list[str],
    dry_mode: str,
) -> dict[str, Any]:
    paths = [device for chain in chains for device in chain["devices"]]
    dependencies = sorted({device["name"] for device in paths})
    output_macro = "OUT" if rack_type != "midi_effect_rack" else None
    exclusions = [f"macro:{macro['name']}" for macro in macros if macro["exclude_from_randomization"]]
    for device in paths:
        definition = get_device(device["registry_id"])
        for parameter_id in device["settings"]:
            if definition.parameters[parameter_id].safety_critical:
                exclusions.append(f"parameter:{device['path']}:{parameter_id}")
    blueprint = {
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "blueprint_notice": BLUEPRINT_NOTICE,
        "capability": "ableton_rack_blueprint",
        "native_format": False,
        "rack_name": f"{recipe.style}_{family}",
        "family": family,
        "rack_type": rack_type,
        "style": recipe.style,
        "version": "1.0.0",
        "minimum_live_version": recipe.minimum_live_version,
        "seed": recipe.seed,
        "dependencies": dependencies,
        "intended_sources": intended_sources,
        "topology": {"chains": chains},
        "input_assumptions": {
            "signal_type": "midi" if rack_type != "audio_effect_rack" else "audio",
            "description": (
                "Receives balanced audio with at least 6 dB headroom."
                if rack_type == "audio_effect_rack"
                else "Receives finite note events on standard MIDI channels."
            ),
            "incoming_note_behavior": (
                "not_applicable_audio" if rack_type == "audio_effect_rack" else "notes_are_processed_in_arrival_order"
            ),
            "outgoing_note_behavior": (
                "not_applicable_audio"
                if rack_type != "midi_effect_rack"
                else "each_generated_note_has_a_bounded_note_off_and_velocity_1_to_127"
            ),
        },
        "dry_strategy": {
            "mode": dry_mode,
            "details": (
                "Audio dry continuity is explicit and never inferred from a device preset."
                if rack_type == "audio_effect_rack"
                else "MIDI and instrument blueprints do not claim an audio dry/wet path."
            ),
        },
        "gain_staging": {
            "input_headroom_db": -6.0 if rack_type != "midi_effect_rack" else None,
            "output_ceiling_db": -1.0 if rack_type != "midi_effect_rack" else None,
            "output_trim_macro": output_macro,
            "details": (
                "A dedicated Utility OUT trim precedes a fixed safety limiter."
                if output_macro
                else "No audio gain or output trim exists in this MIDI-only blueprint."
            ),
        },
        "behavior_notes": (
            {
                "latency": "MIDI scheduling follows the documented stock-device stages; verify timing after manual construction.",
                "tail": "not_applicable_no_audio_tail; every transformed note has a bounded note-off.",
                "mono": "MIDI note processing is independent of an audio mono channel layout.",
                "stereo": "not_applicable_no_audio_stereo_field.",
                "low_frequency": "The declared Scale range bounds low MIDI pitches before the receiving instrument.",
                "bypass": "Disable the rack or return all macros to INIT for identity-oriented bounded processing.",
            }
            if rack_type == "midi_effect_rack"
            else {
                "latency": "Stock-device latency only; re-check after manual construction in Live.",
                "tail": "Bounded feedback and decay values; freeze or print tails deliberately.",
                "mono": "Mono input remains centered unless a documented spatial control is raised.",
                "stereo": "Stereo widening is bounded and excludes low-frequency safety controls.",
                "low_frequency": "Bass is protected by conservative width and filtering decisions.",
                "bypass": "Disable the rack or return all macros to INIT for the documented neutral state.",
            }
        ),
        "macros": macros,
        "macro_variations": _variations(macros),
        "randomization_exclusions": sorted(set(exclusions)),
        "validation_declarations": {
            "schema": "required",
            "registry": "required",
            "structural": "required",
            "ableton_open": "not_performed_native_export_gated",
            "listening_test": "not_performed_native_export_gated",
            "native_export_gate": "closed",
        },
    }
    return blueprint


def _age_machine(recipe: RackBlueprintRecipe) -> dict[str, Any]:
    hazy = recipe.style == "HAZY"
    rng = _rng(recipe, "AGE_MACHINE")
    if hazy:
        dry = _chain("dry", "Dry Anchor", "unprocessed_reference", [], level_db=-3.0, pass_through=True)
        wet_devices = [
            _device("worn", "auto_filter", "tone", {"filter_type": "low_pass", "frequency_hz": round(6100.0 + rng.random() * 200.0, 3), "resonance_percent": 16.0, "lfo_amount_percent": 8.0, "lfo_rate_hz": 0.09, "drive_db": 0.0}),
            _device("worn", "saturator", "patina", {"curve_type": "soft_sine", "drive_db": 3.5, "output_db": -3.5, "soft_clip": True, "dry_wet_percent": 62.0}),
            _device("worn", "echo", "memory", {"mode": "stereo", "left_time_sixteenths": 5, "right_time_sixteenths": 7, "feedback_percent": 24.0, "filter_frequency_hz": 4200.0, "modulation_percent": 18.0, "dry_wet_percent": 16.0}),
            _device("worn", "auto_pan", "wander", {"amount_percent": 12.0, "rate_hz": 0.07, "phase_degrees": 110.0, "shape_percent": 24.0}),
            _device("worn", "utility", "output", {"gain_db": -3.0, "width_percent": 118.0, "bass_mono": True, "bass_mono_frequency_hz": 140.0, "mute": False}),
            _device("worn", "limiter", "safety", {"input_gain_db": 0.0, "ceiling_db": -1.0, "release_ms": 300.0, "stereo_link_percent": 100.0}),
        ]
        chains = [dry, _chain("worn", "Worn Memory", "colored_parallel", wet_devices, level_db=-5.0)]
        p = "chains/worn/devices/"
        macro_specs = [
            ("AGE", [_target(p+"tone", "frequency_hz", 2500, 12000, 12000, "darkens the memory layer", inverse=True), _target(p+"patina", "drive_db", 0, 14, 0, "adds bounded wear")]),
            ("DRIFT", [_target(p+"wander", "amount_percent", 0, 42, 0, "slow level drift"), _target(p+"memory", "modulation_percent", 0, 38, 0, "delay drift")]),
            ("DUST", [_target(p+"patina", "drive_db", 0, 18, 0, "harmonic dust"), _target(p+"patina", "dry_wet_percent", 35, 82, 35, "dust blend")]),
            ("FOCUS", [_target(p+"tone", "resonance_percent", 8, 38, 8, "filter emphasis")]),
            ("BLOOM", [_target(p+"memory", "dry_wet_percent", 0, 34, 0, "echo presence"), _target(p+"memory", "feedback_percent", 8, 48, 8, "bounded repeats")]),
            ("WIDTH", [_target(p+"output", "width_percent", 100, 145, 100, "upper-band width")]),
            ("WOW", [_target(p+"wander", "rate_hz", 0.03, 0.4, 0.03, "wow speed")]),
            ("TONE", [_target(p+"tone", "frequency_hz", 1800, 16000, 16000, "tone contour", inverse=True)]),
            ("ECHO", [_target(p+"memory", "feedback_percent", 0, 55, 0, "feedback")]),
            ("SAT", [_target(p+"patina", "drive_db", 0, 12, 0, "saturation")]),
            ("BLEND", [_target(p+"patina", "dry_wet_percent", 0, 80, 0, "effect blend")]),
            ("OUT", [_target(p+"output", "gain_db", -12, 6, -3, "final trim")]),
        ]
        dry_mode = "parallel_dry_chain"
    else:
        devices = [
            _device("main", "auto_filter", "focus", {"filter_type": "band_pass", "frequency_hz": 4800.0, "resonance_percent": 12.0, "lfo_amount_percent": 0.0, "lfo_rate_hz": 0.2, "drive_db": 2.0}),
            _device("main", "saturator", "edge", {"curve_type": "medium_curve", "drive_db": round(4.0+rng.random(), 3), "output_db": -4.5, "soft_clip": True, "dry_wet_percent": 70.0}),
            _device("main", "auto_pan", "pulse", {"amount_percent": 0.0, "rate_hz": 2.0, "phase_degrees": 180.0, "shape_percent": 58.0}),
            _device("main", "echo", "bloom", {"mode": "stereo", "left_time_sixteenths": 2, "right_time_sixteenths": 3, "feedback_percent": 0.0, "filter_frequency_hz": 6200.0, "modulation_percent": 0.0, "dry_wet_percent": 0.0}),
            _device("main", "utility", "output", {"gain_db": -3.0, "width_percent": 92.0, "bass_mono": True, "bass_mono_frequency_hz": 160.0, "mute": False}),
            _device("main", "limiter", "safety", {"input_gain_db": 0.0, "ceiling_db": -1.0, "release_ms": 220.0, "stereo_link_percent": 100.0}),
        ]
        chains = [_chain("main", "Age Circuit", "serial_processing", devices)]
        p = "chains/main/devices/"
        macro_specs = [
            ("AGE", [_target(p+"focus", "frequency_hz", 900, 11000, 11000, "spectral age", inverse=True), _target(p+"edge", "drive_db", 0, 16, 0, "edge density")]),
            ("DRIFT", [_target(p+"pulse", "amount_percent", 0, 72, 0, "rhythmic drift"), _target(p+"pulse", "shape_percent", 30, 88, 30, "drift contour")]),
            ("DUST", [_target(p+"edge", "drive_db", 0, 20, 0, "distortion dust"), _target(p+"edge", "dry_wet_percent", 25, 88, 25, "dust blend")]),
            ("FOCUS", [_target(p+"focus", "resonance_percent", 5, 50, 5, "resonant focus")]),
            ("WOW", [_target(p+"pulse", "rate_hz", 0.05, 1.8, 0.05, "bounded wow"), _target(p+"pulse", "amount_percent", 0, 38, 0, "wow depth")]),
            ("BLOOM", [_target(p+"bloom", "dry_wet_percent", 0, 28, 0, "short bloom"), _target(p+"bloom", "feedback_percent", 0, 34, 0, "bounded bloom tail")]),
            ("WIDTH", [_target(p+"output", "width_percent", 65, 115, 100, "bounded width"), _target(p+"pulse", "phase_degrees", 90, 180, 180, "stereo motion phase")]),
            ("TONE", [_target(p+"focus", "drive_db", 0, 10, 0, "filter drive")]),
            ("GRIT", [_target(p+"edge", "drive_db", 0, 12, 0, "grit")]),
            ("SHAPE", [_target(p+"pulse", "shape_percent", 0, 90, 0, "motion shape")]),
            ("MOTION", [_target(p+"pulse", "rate_hz", 0.1, 8.0, 0.1, "motion speed")]),
            ("OUT", [_target(p+"output", "gain_db", -12, 6, -3, "final trim")]),
        ]
        dry_mode = "serial_mix"
    macros = [_macro(i, name, targets, recipe.style, output=name == "OUT") for i, (name, targets) in enumerate(macro_specs, 1)]
    return _base_blueprint(recipe, "AGE_MACHINE", "audio_effect_rack", chains, macros, intended_sources=["drums", "percussion", "tonal_loops", "field_textures"], dry_mode=dry_mode)


def _rhythm_fracture(recipe: RackBlueprintRecipe) -> dict[str, Any]:
    hazy = recipe.style == "HAZY"
    rng = _rng(recipe, "RHYTHM_FRACTURE")
    chain_id = "fracture"
    devices = [
        _device(chain_id, "beat_repeat", "repeat", {"interval_sixteenths": 8 if hazy else 4, "offset_sixteenths": 1 if hazy else 0, "chance_percent": round((18.0 if hazy else 28.0) + rng.random() * 2.0, 3), "gate_sixteenths": 3, "grid_sixteenths": 2 if hazy else 1, "variation_percent": 24.0 if hazy else 12.0, "pitch_semitones": -5.0 if hazy else 0.0, "output_mode": "mix", "volume_db": -8.0, "decay_percent": 28.0}),
        _device(chain_id, "saturator", "impact", {"curve_type": "soft_sine" if hazy else "hard_curve", "drive_db": 2.0 if hazy else 5.0, "output_db": -5.0, "soft_clip": True, "dry_wet_percent": 45.0}),
        _device(chain_id, "auto_filter", "window", {"filter_type": "low_pass" if hazy else "high_pass", "frequency_hz": 7200.0 if hazy else 120.0, "resonance_percent": 14.0, "lfo_amount_percent": 0.0, "lfo_rate_hz": 0.25, "drive_db": 0.0}),
    ]
    if hazy:
        devices.append(_device(chain_id, "echo", "ghost", {"mode": "ping_pong", "left_time_sixteenths": 3, "right_time_sixteenths": 5, "feedback_percent": 18.0, "filter_frequency_hz": 3600.0, "modulation_percent": 10.0, "dry_wet_percent": 12.0}))
    devices.extend([
        _device(chain_id, "utility", "output", {"gain_db": -4.0, "width_percent": 100.0 if not hazy else 122.0, "bass_mono": True, "bass_mono_frequency_hz": 150.0, "mute": False}),
        _device(chain_id, "limiter", "safety", {"input_gain_db": 0.0, "ceiling_db": -1.0, "release_ms": 180.0, "stereo_link_percent": 100.0}),
    ])
    chains = ([_chain("dry", "Dry Pulse", "unprocessed_reference", [], level_db=-2.0, pass_through=True)] if hazy else []) + [_chain(chain_id, "Fracture", "rhythmic_processing", devices, level_db=-4.0 if hazy else 0.0)]
    p = f"chains/{chain_id}/devices/"
    macro_specs = [
        ("RATE", [_target(p+"repeat", "interval_sixteenths", 1, 16, 8, "repeat interval")]),
        ("GATE", [_target(p+"repeat", "gate_sixteenths", 1, 12, 3, "repeat gate"), _target(p+"repeat", "decay_percent", 0, 75, 0, "repeat decay")]),
        ("REPEAT", [_target(p+"repeat", "chance_percent", 0, 70, 0, "repeat probability"), _target(p+"repeat", "variation_percent", 0, 60, 0, "repeat variation")]),
        ("OFFSET", [_target(p+"repeat", "offset_sixteenths", 0, 12, 0, "repeat offset")]),
        ("MUTATE", [_target(p+"repeat", "variation_percent", 0, 72, 0, "bounded mutation"), _target(p+"repeat", "pitch_semitones", -7, 7, 0, "repeat pitch")]),
        ("TONE", [_target(p+"window", "frequency_hz", 180, 14000, 14000 if hazy else 180, "filter window")]),
        ("IMPACT", [_target(p+"impact", "drive_db", 0, 15, 0, "transient density"), _target(p+"impact", "dry_wet_percent", 0, 75, 0, "impact blend")]),
        ("GRID", [_target(p+"repeat", "grid_sixteenths", 1, 8, 4, "repeat grid")]),
        ("FILTER", [_target(p+"window", "resonance_percent", 0, 46, 0, "filter focus"), _target(p+"window", "drive_db", 0, 8, 0, "filter drive")]),
        ("SPACE", [_target(p+"ghost", "dry_wet_percent", 0, 28, 0, "ghost delay") if hazy else _target(p+"window", "lfo_amount_percent", 0, 28, 0, "filter movement")]),
        ("MIX", [_target(p+"impact", "dry_wet_percent", 0, 100, 0, "processed blend")]),
        ("OUT", [_target(p+"output", "gain_db", -12, 6, -4, "final trim")]),
    ]
    macros = [_macro(i, name, targets, recipe.style, output=name == "OUT") for i, (name, targets) in enumerate(macro_specs, 1)]
    return _base_blueprint(recipe, "RHYTHM_FRACTURE", "audio_effect_rack", chains, macros, intended_sources=["drums", "percussion", "short_tonal_events"], dry_mode="parallel_dry_chain" if hazy else "serial_mix")


def _operator_rack(recipe: RackBlueprintRecipe, family: str) -> dict[str, Any]:
    hazy = recipe.style == "HAZY"
    pad = family == "OPERATOR_MEMORY_PAD"
    rng = _rng(recipe, family)
    chain_id = "instrument"
    devices: list[dict[str, Any]] = []
    if hazy and pad:
        devices.append(_device(chain_id, "chord", "voicing", {**{f"shift_{i}_semitones": (7 if i == 1 else 12 if i == 2 else 0) for i in range(1, 7)}, **{f"shift_{i}_velocity_percent": (72.0 if i <= 2 else 100.0) for i in range(1, 7)}, **{f"shift_{i}_chance_percent": 100.0 for i in range(1, 7)}, "strum_ms": 22.0, "tension_percent": 15.0, "crescendo_percent": -8.0, "use_current_scale": True}))
    devices.append(_device(chain_id, "scale", "scale_guard", {"scale_name": "dorian" if hazy else "minor", "base_note": "D" if hazy else "A", "use_current_scale": True, "transpose_semitones": 0, "fold": False, "lowest_note": 24, "range_semitones": 72}))
    devices.append(_device(chain_id, "operator", "synth", _operator_settings(recipe.style, family, rng)))
    devices.append(_device(chain_id, "saturator", "body", {"curve_type": "soft_sine" if hazy else "analog_clip", "drive_db": 2.0 if pad else 4.0, "output_db": -4.0, "soft_clip": True, "dry_wet_percent": 55.0}))
    if pad:
        devices.append(_device(chain_id, "hybrid_reverb", "space", {"algorithm": "dark_hall" if hazy else "quartz", "decay_seconds": 4.8 if hazy else 2.7, "size_percent": 72.0, "vintage_percent": 44.0 if hazy else 0.0, "bass_mono": True, "dry_wet_percent": 24.0}))
    elif hazy:
        devices.append(_device(chain_id, "echo", "shadow", {"mode": "stereo", "left_time_sixteenths": 3, "right_time_sixteenths": 3, "feedback_percent": 12.0, "filter_frequency_hz": 2200.0, "modulation_percent": 6.0, "dry_wet_percent": 8.0}))
    devices.extend([
        _device(chain_id, "utility", "output", {"gain_db": -5.0, "width_percent": 100.0 if not pad else 118.0, "bass_mono": True, "bass_mono_frequency_hz": 150.0, "mute": False}),
        _device(chain_id, "limiter", "safety", {"input_gain_db": 0.0, "ceiling_db": -1.0, "release_ms": 260.0, "stereo_link_percent": 100.0}),
    ])
    p = f"chains/{chain_id}/devices/"
    space_path = p + ("space" if pad else "shadow" if hazy else "body")
    body_targets = [_target(p+"synth", "oscillator_a_level_db", -18, 0, -5, "carrier body"), _target(p+"body", "drive_db", 0, 12, 0, "downstream density")]
    fm_targets = [_target(p+"synth", "oscillator_b_level_db", -60, -8, -60, "FM depth"), _target(p+"synth", "oscillator_c_level_db", -60, -16, -60, "secondary color")]
    bite_targets = [_target(p+"synth", "filter_resonance_percent", 0, 55, 0, "filter bite"), _target(p+"body", "drive_db", 0, 16, 0, "effect bite")]
    filter_targets = [_target(p+"synth", "filter_frequency_hz", 180, 12000, 12000, "synthesis cutoff", inverse=True), _target(p+"body", "dry_wet_percent", 25, 75, 25, "post-filter body")]
    env_targets = [_target(p+"synth", "filter_envelope_percent", -20, 80, 0, "filter envelope"), _target(p+"synth", "filter_decay_ms", 120, 5200, 500, "envelope time")]
    motion_targets = [_target(p+"synth", "lfo_amount_percent", 0, 28, 0, "synthesis motion"), _target(p+"synth", "lfo_rate_hz", 0.05, 5.0, 0.05, "motion rate")]
    morph_targets = [_target(p+"synth", "filter_frequency_hz", 300, 9000, 9000, "synthesis tone", inverse=True), _target(space_path, "dry_wet_percent", 0, 42 if pad else 18 if hazy else 72, 0, "downstream effect morph")]
    width_targets = [_target(p+"synth", "spread_percent", 0, 48 if pad else 12, 0, "oscillator spread"), _target(p+"output", "width_percent", 80, 135 if pad else 105, 100, "output width")]
    attack_targets = [_target(p+"synth", "oscillator_a_attack_ms", 0, 2400 if pad else 80, 0, "carrier attack")]
    release_targets = [_target(p+"synth", "oscillator_a_release_ms", 80, 7500 if pad else 1400, 260, "carrier release")]
    tension_targets = [_target(p+"synth", "oscillator_d_level_db", -60, -18, -60, "upper operator tension"), _target(p+"body", "drive_db", 0, 9, 0, "downstream tension")]
    tail_targets = [_target(space_path, "decay_seconds", 0.3, 8.0, 1.5, "reverb tail") if pad else _target(space_path, "dry_wet_percent", 0, 35 if hazy else 75, 0, "effect tail")]
    if pad:
        macro_specs = [
            ("COLOR", body_targets), ("FM", fm_targets),
            ("HARMONICS", [_target(p+"synth", "oscillator_c_level_db", -60, -8, -60, "upper harmonics")]),
            ("FILTER", filter_targets), ("ATTACK", attack_targets), ("RELEASE", release_targets),
            ("DRIFT", motion_targets), ("MOTION", env_targets), ("AGE", bite_targets),
            ("BLOOM", tail_targets), ("WIDTH", width_targets), ("MORPH", morph_targets),
            ("VELOCITY", [_target(p+"synth", "velocity_to_volume_percent", 0, 72, 0, "velocity response")]),
            ("TENSION", tension_targets), ("BODY", body_targets),
            ("OUT", [_target(p+"output", "gain_db", -12, 6, -5, "final trim")]),
        ]
    else:
        macro_specs = [
            ("BODY", body_targets), ("FM", fm_targets),
            ("SUB", [_target(p+"synth", "oscillator_c_level_db", -60, -8, -60, "sub oscillator")]),
            ("BITE", bite_targets), ("FILTER", filter_targets), ("ENV", env_targets),
            ("GLIDE", [_target(p+"synth", "glide_ms", 0, 640, 0, "portamento")]),
            ("MOTION", motion_targets), ("DIRT", tension_targets), ("SPACE", tail_targets),
            ("WIDTH_HI", width_targets), ("ATTACK", attack_targets), ("RELEASE", release_targets),
            ("VELOCITY", [_target(p+"synth", "velocity_to_volume_percent", 0, 72, 0, "velocity response")]),
            ("MORPH", morph_targets),
            ("OUT", [_target(p+"output", "gain_db", -12, 6, -5, "final trim")]),
        ]
    macros = [_macro(i, name, targets, recipe.style, output=name == "OUT") for i, (name, targets) in enumerate(macro_specs, 1)]
    return _base_blueprint(recipe, family, "operator_instrument_rack", [_chain(chain_id, "Operator Voice", "midi_to_audio_instrument", devices)], macros, intended_sources=["played_midi", "sequenced_midi", "velocity_sensitive_notes"], dry_mode="not_applicable")


def _midi_mutator(recipe: RackBlueprintRecipe) -> dict[str, Any]:
    hazy = recipe.style == "HAZY"
    rng = _rng(recipe, "MIDI_PATTERN_MUTATOR")
    chain_id = "midi"
    order = ["random", "scale", "chord", "arpeggiator", "note_length", "velocity"] if hazy else ["scale", "chord", "arpeggiator", "random", "note_length", "velocity"]
    settings = {
        "scale": {"scale_name": "dorian" if hazy else "minor", "base_note": "D" if hazy else "A", "use_current_scale": True, "transpose_semitones": 0, "fold": True, "lowest_note": 24, "range_semitones": 72},
        "chord": {**{f"shift_{i}_semitones": (7 if i == 1 else 12 if i == 2 else 0) for i in range(1, 7)}, **{f"shift_{i}_velocity_percent": (68.0 if i <= 2 else 100.0) for i in range(1, 7)}, **{f"shift_{i}_chance_percent": 100.0 for i in range(1, 7)}, "strum_ms": 12.0 if hazy else 0.0, "tension_percent": 10.0 if hazy else 0.0, "crescendo_percent": 0.0, "use_current_scale": True},
        "arpeggiator": {"style": "up_down" if hazy else "up", "rate_sixteenths": 2 if hazy else 4, "gate_percent": 74.0, "distance_semitones": 12, "steps": 2 if hazy else 1, "retrigger": "note", "use_current_scale": True},
        "random": {"chance_percent": round((8.0 if hazy else 0.0) + rng.random() * (2.0 if hazy else 1.0), 3), "choices": 3 if hazy else 2, "interval_semitones": 2 if hazy else 1, "mode": "alternate" if hazy else "random", "sign": "bipolar", "use_current_scale": True},
        "note_length": {"trigger_source": "note_on", "gate_percent": 84.0, "length_sixteenths": 2, "release_velocity": 64, "release_decay_ms": 0.0},
        "velocity": {"operation": "both", "mode": "clip", "lowest": 1, "range": 127, "out_low": 38 if hazy else 48, "out_high": 108, "random_amount": 0},
    }
    devices = [_device(chain_id, identifier, identifier, settings[identifier]) for identifier in order]
    p = f"chains/{chain_id}/devices/"
    macro_specs = [
        ("ROOT", [_target(p+"scale", "transpose_semitones", -12, 12, 0, "root displacement")]),
        ("CHORD", [_target(p+"chord", "shift_1_velocity_percent", 0, 100, 0, "first chord tone"), _target(p+"chord", "shift_2_velocity_percent", 0, 100, 0, "second chord tone")]),
        ("STRUM", [_target(p+"chord", "strum_ms", 0, 180, 0, "bounded chord spread")]),
        ("RATE", [_target(p+"arpeggiator", "rate_sixteenths", 1, 8, 4, "arpeggio rate")]),
        ("GATE", [_target(p+"arpeggiator", "gate_percent", 20, 130, 100, "arpeggio gate"), _target(p+"note_length", "gate_percent", 20, 130, 100, "final note gate")]),
        ("MUTATE", [_target(p+"random", "chance_percent", 0, 38, 0, "bounded pitch mutation"), _target(p+"random", "choices", 1, 7, 1, "mutation choices")]),
        ("INTERVAL", [_target(p+"random", "interval_semitones", 1, 7, 1, "mutation interval")]),
        ("LENGTH", [_target(p+"note_length", "length_sixteenths", 1, 8, 4, "note duration")]),
        ("VELOCITY", [_target(p+"velocity", "out_low", 24, 72, 48, "velocity floor"), _target(p+"velocity", "out_high", 82, 118, 108, "velocity ceiling")]),
        ("DYNAMICS", [_target(p+"velocity", "random_amount", 0, 28, 0, "bounded velocity deviation"), _target(p+"chord", "crescendo_percent", -35, 35, 0, "chord dynamics")]),
        ("TIMING", [_target(p+"chord", "strum_ms", 0, 90, 0, "role-aware timing"), _target(p+"arpeggiator", "gate_percent", 55, 110, 100, "timing articulation")]),
        ("RANGE", [_target(p+"scale", "lowest_note", 24, 60, 24, "lowest output note"), _target(p+"scale", "range_semitones", 24, 84, 72, "allowed note span")]),
    ]
    macros = [_macro(i, name, targets, recipe.style) for i, (name, targets) in enumerate(macro_specs, 1)]
    return _base_blueprint(recipe, "MIDI_PATTERN_MUTATOR", "midi_effect_rack", [_chain(chain_id, "MIDI Transform", "midi_processing", devices)], macros, intended_sources=["single_notes", "held_chords", "short_midi_phrases"], dry_mode="not_applicable")


def generate_rack_blueprints(recipe: RackBlueprintRecipe) -> list[dict[str, Any]]:
    """Generate the exact Milestone 3A catalog for one style."""
    require_capability("ableton_rack_blueprint")
    generated = [
        _age_machine(recipe),
        _rhythm_fracture(recipe),
        _operator_rack(recipe, "OPERATOR_SUB_FORM"),
        _operator_rack(recipe, "OPERATOR_MEMORY_PAD"),
        _midi_mutator(recipe),
    ]
    return [RackBlueprint.from_data(blueprint).to_data() for blueprint in generated]


def write_blueprint(path: str | Path, blueprint: dict[str, Any]) -> Path:
    """Write canonical UTF-8 JSON after strict blueprint validation."""
    model = RackBlueprint.from_data(blueprint)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model.to_data(), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return output


def load_blueprint(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("rack blueprint must be valid UTF-8 JSON") from error
    return RackBlueprint.from_data(data).to_data()


def inventory_families(blueprints: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(blueprint["family"] for blueprint in blueprints)
