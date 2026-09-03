"""Canonical recipe inputs and profile routing for deterministic generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .capabilities import require_capability

ROOTS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
SCALES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
}
HAZY_MODES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
}
HAZY_ARCHETYPES = {
    "modal_pedal": (1, 4, 2, 7),
    "suspended_arc": (1, 5, 4, 2),
    "open_cycle": (1, 7, 3, 4),
}
PROFILE_VERSIONS = {"DRUIID": "DRUIID_R1", "HAZY": "HAZY_R1"}
VARIATION_LEVELS = {"A": 0.0, "B": 0.5, "C": 1.0}


def canonical_json(data: dict[str, Any]) -> str:
    """Serialize recipe data into the stable representation used for seeds."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def route_profile(style: str) -> str:
    """Route only profiles explicitly implemented by this milestone."""
    if style == "DRUIID":
        require_capability("druiid_midi_essentials")
        return PROFILE_VERSIONS[style]
    if style == "HAZY":
        require_capability("hazy_midi_essentials")
        return PROFILE_VERSIONS[style]
    raise ValueError(f"unsupported style profile: {style}")


@dataclass(frozen=True)
class MidiEssentialsRecipe:
    """Validated, canonical inputs for a DRUIID MIDI Essentials pack."""

    seed: int
    root: str = "A"
    scale: str = "minor"
    bpm: int = 120
    bars: int = 8
    progression: tuple[int, ...] = (1, 6, 4, 5)
    style: str = "DRUIID"
    upper_mutation: float = 0.5
    bass_mutation: float = 0.5
    motif_mutation: float = 0.5
    rhythm_mutation: float = 0.5
    humanize_ticks: int = 4

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "progression", tuple(self.progression))
        except TypeError as error:
            raise ValueError("progression must be an iterable of scale degrees") from error
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed <= 9999:
            raise ValueError("seed must be an integer from 0 to 9999")
        if self.root not in ROOTS:
            raise ValueError(f"root must be one of: {', '.join(ROOTS)}")
        if self.scale not in SCALES:
            raise ValueError(f"scale must be one of: {', '.join(SCALES)}")
        if isinstance(self.bpm, bool) or not isinstance(self.bpm, int) or not 40 <= self.bpm <= 240:
            raise ValueError("bpm must be an integer from 40 to 240")
        if isinstance(self.bars, bool) or not isinstance(self.bars, int) or self.bars <= 0:
            raise ValueError("bars must be a positive integer")
        if not self.progression or any(
            isinstance(degree, bool) or not isinstance(degree, int) or not 1 <= degree <= 7
            for degree in self.progression
        ):
            raise ValueError("progression must contain scale degrees from 1 to 7")
        if len(self.progression) > self.bars * 4:
            raise ValueError("progression cannot contain more changes than quarter notes in the clip")
        for name in ("upper_mutation", "bass_mutation", "motif_mutation", "rhythm_mutation"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")
            object.__setattr__(self, name, 0.0 if value == 0 else float(value))
        if (
            isinstance(self.humanize_ticks, bool)
            or not isinstance(self.humanize_ticks, int)
            or not 0 <= self.humanize_ticks <= 12
        ):
            raise ValueError("humanize_ticks must be an integer from 0 to 12")
        if self.style != "DRUIID":
            raise ValueError("MidiEssentialsRecipe requires the DRUIID style")
        route_profile(self.style)

    @property
    def profile_version(self) -> str:
        return route_profile(self.style)

    @property
    def key(self) -> str:
        return f"{self.root} {self.scale}"

    def canonical_data(self) -> dict[str, Any]:
        return {
            "bars": self.bars,
            "bass_mutation": float(self.bass_mutation),
            "bpm": self.bpm,
            "humanize_ticks": self.humanize_ticks,
            "motif_mutation": float(self.motif_mutation),
            "progression": list(self.progression),
            "rhythm_mutation": float(self.rhythm_mutation),
            "root": self.root,
            "scale": self.scale,
            "seed": self.seed,
            "style": self.style,
            "upper_mutation": float(self.upper_mutation),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.canonical_data())

    def base_seed_data(self) -> dict[str, Any]:
        """Return identity inputs shared by every independently mutable role."""
        return {
            "bars": self.bars,
            "bpm": self.bpm,
            "progression": list(self.progression),
            "root": self.root,
            "scale": self.scale,
            "seed": self.seed,
            "style": self.style,
        }

    def role_seed_data(self, role: str) -> dict[str, Any]:
        """Return seed inputs isolated to one role's creative controls."""
        controls = {
            "chords": self.upper_mutation,
            "bass": self.bass_mutation,
            "motif": self.motif_mutation,
            "drums": self.rhythm_mutation,
        }
        try:
            mutation = controls[role]
        except KeyError as error:
            raise ValueError(f"unknown recipe role: {role}") from error
        return {
            **self.base_seed_data(),
            "humanize_ticks": self.humanize_ticks,
            "mutation": float(mutation),
            "role": role,
        }

    def mutation_for(self, role: str, variation: str) -> float:
        if variation not in VARIATION_LEVELS:
            raise ValueError("variation must be A, B, or C")
        controls = {
            "chords": self.upper_mutation,
            "bass": self.bass_mutation,
            "motif": self.motif_mutation,
            "drums": self.rhythm_mutation,
        }
        try:
            control = controls[role]
        except KeyError as error:
            raise ValueError(f"unknown recipe role: {role}") from error
        return round(float(control) * VARIATION_LEVELS[variation], 6)


@dataclass(frozen=True)
class HazyMidiRecipe:
    """Validated, canonical controls for an original HAZY MIDI Essentials pack."""

    seed: int
    root: str = "D"
    mode: str = "dorian"
    bpm: int = 92
    bars: int = 8
    harmonic_archetype: str = "modal_pedal"
    progression: tuple[int, ...] | None = None
    color_amount: float = 0.65
    ambiguity: float = 0.6
    tension: float = 0.4
    pedal_preference: float = 0.7
    common_tone_preference: float = 0.75
    groove_drift: int = 6
    chord_mutation: float = 0.55
    bass_mutation: float = 0.45
    motif_mutation: float = 0.5
    arpeggio_mutation: float = 0.55
    drum_mutation: float = 0.5
    style: str = "HAZY"

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed <= 9999:
            raise ValueError("seed must be an integer from 0 to 9999")
        if self.root not in ROOTS:
            raise ValueError(f"root must be one of: {', '.join(ROOTS)}")
        if self.mode not in HAZY_MODES:
            raise ValueError(f"mode must be one of: {', '.join(HAZY_MODES)}")
        if self.harmonic_archetype not in HAZY_ARCHETYPES:
            raise ValueError(
                f"harmonic_archetype must be one of: {', '.join(HAZY_ARCHETYPES)}"
            )
        selected = HAZY_ARCHETYPES[self.harmonic_archetype] if self.progression is None else self.progression
        try:
            normalized_progression = tuple(selected)
        except TypeError as error:
            raise ValueError("progression must be an iterable of scale degrees") from error
        if not normalized_progression or any(
            isinstance(degree, bool) or not isinstance(degree, int) or not 1 <= degree <= 7
            for degree in normalized_progression
        ):
            raise ValueError("progression must contain scale degrees from 1 to 7")
        object.__setattr__(self, "progression", normalized_progression)
        if isinstance(self.bpm, bool) or not isinstance(self.bpm, int) or not 40 <= self.bpm <= 240:
            raise ValueError("bpm must be an integer from 40 to 240")
        if isinstance(self.bars, bool) or not isinstance(self.bars, int) or self.bars <= 0:
            raise ValueError("bars must be a positive integer")
        if len(normalized_progression) > self.bars * 4:
            raise ValueError("progression cannot contain more changes than quarter notes in the clip")
        controls = (
            "color_amount",
            "ambiguity",
            "tension",
            "pedal_preference",
            "common_tone_preference",
            "chord_mutation",
            "bass_mutation",
            "motif_mutation",
            "arpeggio_mutation",
            "drum_mutation",
        )
        for name in controls:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")
            object.__setattr__(self, name, 0.0 if value == 0 else float(value))
        if (
            isinstance(self.groove_drift, bool)
            or not isinstance(self.groove_drift, int)
            or not 0 <= self.groove_drift <= 12
        ):
            raise ValueError("groove_drift must be an integer from 0 to 12 ticks")
        if self.style != "HAZY":
            raise ValueError("HazyMidiRecipe requires the HAZY style")
        route_profile(self.style)

    @property
    def profile_version(self) -> str:
        return route_profile(self.style)

    @property
    def scale(self) -> str:
        """Expose the selected mode through the shared manifest scale field."""
        return self.mode

    @property
    def key(self) -> str:
        return f"{self.root} {self.mode}"

    def canonical_data(self) -> dict[str, Any]:
        return {
            "ambiguity": float(self.ambiguity),
            "arpeggio_mutation": float(self.arpeggio_mutation),
            "bars": self.bars,
            "bass_mutation": float(self.bass_mutation),
            "bpm": self.bpm,
            "chord_mutation": float(self.chord_mutation),
            "color_amount": float(self.color_amount),
            "common_tone_preference": float(self.common_tone_preference),
            "drum_mutation": float(self.drum_mutation),
            "groove_drift": self.groove_drift,
            "harmonic_archetype": self.harmonic_archetype,
            "mode": self.mode,
            "motif_mutation": float(self.motif_mutation),
            "pedal_preference": float(self.pedal_preference),
            "progression": list(self.progression),
            "root": self.root,
            "seed": self.seed,
            "style": self.style,
            "tension": float(self.tension),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.canonical_data())

    def base_seed_data(self) -> dict[str, Any]:
        return {
            "bars": self.bars,
            "bpm": self.bpm,
            "harmonic_archetype": self.harmonic_archetype,
            "mode": self.mode,
            "progression": list(self.progression),
            "root": self.root,
            "seed": self.seed,
            "style": self.style,
        }

    def role_seed_data(self, role: str) -> dict[str, Any]:
        role_controls: dict[str, dict[str, Any]] = {
            "chords": {
                "ambiguity": self.ambiguity,
                "color_amount": self.color_amount,
                "common_tone_preference": self.common_tone_preference,
                "groove_drift": self.groove_drift,
                "mutation": self.chord_mutation,
                "pedal_preference": self.pedal_preference,
                "tension": self.tension,
            },
            "bass": {
                "ambiguity": self.ambiguity,
                "mutation": self.bass_mutation,
                "pedal_preference": self.pedal_preference,
                "tension": self.tension,
            },
            "motif": {
                "ambiguity": self.ambiguity,
                "groove_drift": self.groove_drift,
                "mutation": self.motif_mutation,
                "tension": self.tension,
            },
            "arpeggio": {
                "ambiguity": self.ambiguity,
                "color_amount": self.color_amount,
                "groove_drift": self.groove_drift,
                "mutation": self.arpeggio_mutation,
                "pedal_preference": self.pedal_preference,
            },
            "drums": {
                "groove_drift": self.groove_drift,
                "mutation": self.drum_mutation,
            },
        }
        try:
            controls = role_controls[role]
        except KeyError as error:
            raise ValueError(f"unknown recipe role: {role}") from error
        return {**self.base_seed_data(), **controls, "role": role}

    def mutation_for(self, role: str, variation: str) -> float:
        if variation not in VARIATION_LEVELS:
            raise ValueError("variation must be A, B, or C")
        controls = {
            "chords": self.chord_mutation,
            "bass": self.bass_mutation,
            "motif": self.motif_mutation,
            "arpeggio": self.arpeggio_mutation,
            "drums": self.drum_mutation,
        }
        try:
            control = controls[role]
        except KeyError as error:
            raise ValueError(f"unknown recipe role: {role}") from error
        return round(float(control) * VARIATION_LEVELS[variation], 6)
