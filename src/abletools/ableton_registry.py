"""Closed registry of verified Ableton Live stock devices and blueprint parameters.

The identifiers in this module are Abletools' stable blueprint vocabulary.  Their
display names mirror controls documented in the Ableton Live 12 manual; they are
not native device serialization keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParameterDefinition:
    label: str
    kind: str = "number"
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    neutral: Any = None
    unit: str = ""
    safety_critical: bool = False

    def validate(self, value: Any) -> None:
        if self.kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{self.label} must be boolean")
            return
        if self.kind == "enum":
            if not isinstance(value, str) or value not in self.choices:
                raise ValueError(f"{self.label} must be one of {', '.join(self.choices)}")
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{self.label} must be numeric")
        if self.kind == "integer" and not isinstance(value, int):
            raise ValueError(f"{self.label} must be an integer")
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"{self.label} is below its supported range")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"{self.label} is above its supported range")


@dataclass(frozen=True)
class DeviceDefinition:
    identifier: str
    display_name: str
    stage: str
    minimum_live_version: str
    parameters: dict[str, ParameterDefinition]


def number(
    label: str,
    minimum: float,
    maximum: float,
    neutral: float,
    unit: str = "",
    *,
    safety: bool = False,
) -> ParameterDefinition:
    return ParameterDefinition(label, "number", minimum, maximum, neutral=neutral, unit=unit, safety_critical=safety)


def integer(label: str, minimum: int, maximum: int, neutral: int, unit: str = "") -> ParameterDefinition:
    return ParameterDefinition(label, "integer", minimum, maximum, neutral=neutral, unit=unit)


def choice(label: str, *choices: str, neutral: str | None = None) -> ParameterDefinition:
    return ParameterDefinition(label, "enum", choices=tuple(choices), neutral=neutral or choices[0])


def boolean(label: str, neutral: bool = False) -> ParameterDefinition:
    return ParameterDefinition(label, "boolean", neutral=neutral)


DEVICE_REGISTRY: dict[str, DeviceDefinition] = {}


def _register(identifier: str, display_name: str, stage: str, parameters: dict[str, ParameterDefinition]) -> None:
    DEVICE_REGISTRY[identifier] = DeviceDefinition(identifier, display_name, stage, "12.0", parameters)


_register(
    "utility",
    "Utility",
    "audio_effect",
    {
        "gain_db": number("Gain", -35.0, 12.0, 0.0, "dB", safety=True),
        "width_percent": number("Width", 0.0, 200.0, 100.0, "%"),
        "bass_mono": boolean("Bass Mono"),
        "bass_mono_frequency_hz": number("Bass Mono Frequency", 50.0, 500.0, 120.0, "Hz"),
        "mute": boolean("Mute"),
    },
)
_register(
    "limiter",
    "Limiter",
    "audio_effect",
    {
        "input_gain_db": number("Input Gain", 0.0, 24.0, 0.0, "dB", safety=True),
        "ceiling_db": number("Ceiling", -12.0, 0.0, -1.0, "dB", safety=True),
        "release_ms": number("Release", 1.0, 3000.0, 300.0, "ms"),
        "stereo_link_percent": number("Stereo Link", 0.0, 100.0, 100.0, "%"),
    },
)
_register(
    "auto_filter",
    "Auto Filter",
    "audio_effect",
    {
        "filter_type": choice("Filter Type", "low_pass", "high_pass", "band_pass", "notch", "morph", neutral="low_pass"),
        "frequency_hz": number("Frequency", 20.0, 20000.0, 20000.0, "Hz"),
        "resonance_percent": number("Resonance", 0.0, 100.0, 0.0, "%"),
        "lfo_amount_percent": number("LFO Amount", 0.0, 100.0, 0.0, "%"),
        "lfo_rate_hz": number("LFO Rate", 0.01, 40.0, 0.1, "Hz"),
        "drive_db": number("Drive", 0.0, 12.0, 0.0, "dB"),
    },
)
_register(
    "saturator",
    "Saturator",
    "audio_effect",
    {
        "curve_type": choice("Curve Type", "analog_clip", "soft_sine", "medium_curve", "hard_curve", "digital_clip", neutral="analog_clip"),
        "drive_db": number("Drive", -36.0, 36.0, 0.0, "dB"),
        "output_db": number("Output", -36.0, 0.0, 0.0, "dB", safety=True),
        "soft_clip": boolean("Soft Clip"),
        "dry_wet_percent": number("Dry/Wet", 0.0, 100.0, 100.0, "%"),
    },
)
_register(
    "echo",
    "Echo",
    "audio_effect",
    {
        "mode": choice("Channel Mode", "stereo", "ping_pong", "mid_side", neutral="stereo"),
        "left_time_sixteenths": integer("Left Delay Time", 1, 16, 4, "sixteenths"),
        "right_time_sixteenths": integer("Right Delay Time", 1, 16, 4, "sixteenths"),
        "feedback_percent": number("Feedback", 0.0, 85.0, 0.0, "%", safety=True),
        "filter_frequency_hz": number("Filter Frequency", 50.0, 18000.0, 8000.0, "Hz"),
        "modulation_percent": number("Modulation", 0.0, 100.0, 0.0, "%"),
        "dry_wet_percent": number("Dry/Wet", 0.0, 100.0, 0.0, "%"),
    },
)
_register(
    "hybrid_reverb",
    "Hybrid Reverb",
    "audio_effect",
    {
        "algorithm": choice("Algorithm", "dark_hall", "quartz", "shimmer", "tides", "prism", neutral="dark_hall"),
        "decay_seconds": number("Decay Time", 0.2, 12.0, 1.5, "s", safety=True),
        "size_percent": number("Size", 0.0, 100.0, 50.0, "%"),
        "vintage_percent": number("Vintage", 0.0, 100.0, 0.0, "%"),
        "bass_mono": boolean("Bass Mono", True),
        "dry_wet_percent": number("Dry/Wet", 0.0, 100.0, 0.0, "%"),
    },
)
_register(
    "beat_repeat",
    "Beat Repeat",
    "audio_effect",
    {
        "interval_sixteenths": integer("Interval", 1, 16, 4, "sixteenths"),
        "offset_sixteenths": integer("Offset", 0, 15, 0, "sixteenths"),
        "chance_percent": number("Chance", 0.0, 100.0, 0.0, "%"),
        "gate_sixteenths": integer("Gate", 1, 16, 4, "sixteenths"),
        "grid_sixteenths": integer("Grid", 1, 16, 4, "sixteenths"),
        "variation_percent": number("Variation", 0.0, 100.0, 0.0, "%"),
        "pitch_semitones": number("Pitch", -12.0, 12.0, 0.0, "st"),
        "output_mode": choice("Output Mode", "mix", "insert", "gate", neutral="mix"),
        "volume_db": number("Volume", -36.0, 0.0, -6.0, "dB", safety=True),
        "decay_percent": number("Decay", 0.0, 100.0, 0.0, "%"),
    },
)
_register(
    "auto_pan",
    "Auto Pan",
    "audio_effect",
    {
        "amount_percent": number("Amount", 0.0, 100.0, 0.0, "%"),
        "rate_hz": number("Rate", 0.01, 40.0, 0.25, "Hz"),
        "phase_degrees": number("Phase", 0.0, 360.0, 180.0, "degrees"),
        "shape_percent": number("Shape", 0.0, 100.0, 0.0, "%"),
    },
)

_register(
    "operator",
    "Operator",
    "instrument",
    {
        "algorithm": integer("Algorithm", 1, 11, 1),
        **{
            f"oscillator_{osc}_{parameter}": definition
            for osc in "abcd"
            for parameter, definition in {
                "waveform": choice("Waveform", "sine", "saw_d", "square_d", "triangle", "noise_looped", neutral="sine"),
                "level_db": number("Level", -60.0, 0.0, -60.0, "dB"),
                "coarse": integer("Coarse Ratio", 1, 32, 1),
                "fine": integer("Fine Ratio", 0, 999, 0),
                "fixed": boolean("Fixed Frequency"),
                "fixed_frequency_hz": number("Fixed Frequency", 10.0, 20000.0, 440.0, "Hz"),
                "attack_ms": number("Envelope Attack", 0.0, 10000.0, 5.0, "ms"),
                "decay_ms": number("Envelope Decay", 0.0, 60000.0, 500.0, "ms"),
                "sustain_percent": number("Envelope Sustain", 0.0, 100.0, 100.0, "%"),
                "release_ms": number("Envelope Release", 0.0, 60000.0, 500.0, "ms"),
            }.items()
        },
        "filter_type": choice("Filter Type", "low_pass_12", "low_pass_24", "high_pass_12", "band_pass_12", "notch_12", neutral="low_pass_12"),
        "filter_frequency_hz": number("Filter Frequency", 20.0, 20000.0, 20000.0, "Hz"),
        "filter_resonance_percent": number("Filter Resonance", 0.0, 100.0, 0.0, "%"),
        "filter_envelope_percent": number("Filter Envelope", -100.0, 100.0, 0.0, "%"),
        "filter_drive_db": number("Filter Drive", 0.0, 12.0, 0.0, "dB"),
        "filter_key_tracking_percent": number("Filter Key Tracking", 0.0, 100.0, 100.0, "%"),
        "filter_velocity_percent": number("Filter Velocity", -100.0, 100.0, 0.0, "%"),
        "filter_attack_ms": number("Filter Envelope Attack", 0.0, 10000.0, 5.0, "ms"),
        "filter_decay_ms": number("Filter Envelope Decay", 0.0, 60000.0, 500.0, "ms"),
        "filter_sustain_percent": number("Filter Envelope Sustain", 0.0, 100.0, 100.0, "%"),
        "filter_release_ms": number("Filter Envelope Release", 0.0, 60000.0, 500.0, "ms"),
        "lfo_waveform": choice("LFO Waveform", "sine", "square", "triangle", "saw_up", "saw_down", "sample_hold", neutral="sine"),
        "lfo_rate_hz": number("LFO Rate", 0.01, 30.0, 1.0, "Hz"),
        "lfo_amount_percent": number("LFO Amount", 0.0, 100.0, 0.0, "%"),
        "lfo_destination": choice("LFO Destination", "oscillator_pitch", "filter", "amplitude", neutral="oscillator_pitch"),
        "lfo_sync": boolean("LFO Sync"),
        "lfo_retrigger": boolean("LFO Retrigger", True),
        "pitch_envelope_amount_st": number("Pitch Envelope Amount", -48.0, 48.0, 0.0, "st"),
        "pitch_envelope_attack_ms": number("Pitch Envelope Attack", 0.0, 10000.0, 0.0, "ms"),
        "pitch_envelope_decay_ms": number("Pitch Envelope Decay", 0.0, 60000.0, 100.0, "ms"),
        "pitch_envelope_release_ms": number("Pitch Envelope Release", 0.0, 60000.0, 100.0, "ms"),
        "transpose_semitones": integer("Transpose", -48, 48, 0, "st"),
        "glide_ms": number("Glide", 0.0, 10000.0, 0.0, "ms"),
        "spread_percent": number("Spread", 0.0, 100.0, 0.0, "%"),
        "voices": integer("Voices", 1, 32, 6),
        "velocity_to_volume_percent": number("Velocity to Volume", 0.0, 100.0, 0.0, "%"),
        "master_volume_db": number("Volume", -36.0, 0.0, -12.0, "dB", safety=True),
    },
)

_register(
    "scale",
    "Scale",
    "midi_effect",
    {
        "scale_name": choice("Scale Name", "major", "minor", "dorian", "mixolydian", "lydian", "aeolian", neutral="major"),
        "base_note": choice("Base Note", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B", neutral="C"),
        "use_current_scale": boolean("Use Current Scale", True),
        "transpose_semitones": integer("Transpose", -36, 36, 0, "st"),
        "fold": boolean("Fold"),
        "lowest_note": integer("Lowest Note", 0, 127, 0),
        "range_semitones": integer("Range", 1, 127, 127, "st"),
    },
)
_register(
    "chord",
    "Chord",
    "midi_effect",
    {
        **{f"shift_{index}_semitones": integer(f"Shift {index}", -36, 36, 0, "st") for index in range(1, 7)},
        **{f"shift_{index}_velocity_percent": number(f"Shift {index} Velocity", 0.0, 100.0, 100.0, "%") for index in range(1, 7)},
        **{f"shift_{index}_chance_percent": number(f"Shift {index} Chance", 0.0, 100.0, 100.0, "%") for index in range(1, 7)},
        "strum_ms": number("Strum", 0.0, 1000.0, 0.0, "ms"),
        "tension_percent": number("Tension", 0.0, 100.0, 0.0, "%"),
        "crescendo_percent": number("Crescendo", -100.0, 100.0, 0.0, "%"),
        "use_current_scale": boolean("Use Current Scale", True),
    },
)
_register(
    "arpeggiator",
    "Arpeggiator",
    "midi_effect",
    {
        "style": choice("Style", "up", "down", "up_down", "down_up", "converge", "diverge", "random", neutral="up"),
        "rate_sixteenths": integer("Rate", 1, 16, 4, "sixteenths"),
        "gate_percent": number("Gate", 1.0, 200.0, 100.0, "%"),
        "distance_semitones": integer("Distance", -36, 36, 12, "st"),
        "steps": integer("Steps", 1, 8, 1),
        "retrigger": choice("Retrigger", "off", "note", "beat", neutral="off"),
        "use_current_scale": boolean("Use Current Scale", True),
    },
)
_register(
    "random",
    "Random",
    "midi_effect",
    {
        "chance_percent": number("Chance", 0.0, 100.0, 0.0, "%"),
        "choices": integer("Choices", 1, 24, 1),
        "interval_semitones": integer("Interval", 1, 36, 1, "st"),
        "mode": choice("Mode", "random", "alternate", neutral="random"),
        "sign": choice("Sign", "add", "subtract", "bipolar", neutral="add"),
        "use_current_scale": boolean("Use Current Scale", True),
    },
)
_register(
    "note_length",
    "Note Length",
    "midi_effect",
    {
        "trigger_source": choice("Trigger Source", "note_on", "note_off", neutral="note_on"),
        "gate_percent": number("Gate", 1.0, 200.0, 100.0, "%"),
        "length_sixteenths": integer("Length", 1, 16, 4, "sixteenths"),
        "release_velocity": integer("Release Velocity", 1, 127, 64),
        "release_decay_ms": number("Release Decay", 0.0, 10000.0, 0.0, "ms"),
    },
)
_register(
    "velocity",
    "Velocity",
    "midi_effect",
    {
        "operation": choice("Operation", "both", "drive", "compand", neutral="both"),
        "mode": choice("Mode", "clip", "gate", "fixed", neutral="clip"),
        "lowest": integer("Lowest", 1, 127, 1),
        "range": integer("Range", 1, 127, 127),
        "out_low": integer("Out Low", 1, 127, 1),
        "out_high": integer("Out High", 1, 127, 127),
        "random_amount": integer("Random", 0, 127, 0),
    },
)


def get_device(identifier: str) -> DeviceDefinition:
    try:
        return DEVICE_REGISTRY[identifier]
    except KeyError as error:
        raise ValueError(f"unknown Ableton stock device: {identifier}") from error


def get_parameter(device_identifier: str, parameter_identifier: str) -> ParameterDefinition:
    device = get_device(device_identifier)
    try:
        return device.parameters[parameter_identifier]
    except KeyError as error:
        raise ValueError(f"unknown parameter for {device_identifier}: {parameter_identifier}") from error
