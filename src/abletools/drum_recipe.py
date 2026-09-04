"""Canonical recipes and bounded profiles for deterministic drum synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capabilities import require_capability
from .recipe import PROFILE_VERSIONS, canonical_json

SAMPLE_RATE = 48_000
BIT_DEPTH = 24
CHANNELS = 1


@dataclass(frozen=True)
class DrumFamilySpec:
    """Fixed catalog and practical duration boundary for one drum family."""

    count: int
    minimum_duration: float
    maximum_duration: float
    descriptors: tuple[str, ...]
    parameter_bounds: tuple[tuple[str, float, float], ...]


DRUM_FAMILY_SPECS: dict[str, DrumFamilySpec] = {
    "kick": DrumFamilySpec(
        8,
        0.28,
        0.95,
        ("COMPACT", "DEEP", "PUNCH", "ROUND", "TIGHT", "WEIGHT", "CLICK", "HYBRID"),
        (
            ("body_decay", 5.0, 15.0),
            ("click_mix", 0.05, 0.30),
            ("end_frequency_hz", 38.0, 65.0),
            ("harmonic_mix", 0.03, 0.25),
            ("pitch_decay", 20.0, 55.0),
            ("start_frequency_hz", 95.0, 185.0),
        ),
    ),
    "snare": DrumFamilySpec(
        8,
        0.20,
        0.90,
        ("SNAP", "FRAME", "PLATE", "SHORT", "NOISE", "TONE", "LAYER", "CRACK"),
        (
            ("body_decay", 10.0, 25.0),
            ("body_frequency_hz", 140.0, 300.0),
            ("noise_decay", 7.0, 21.0),
            ("noise_mix", 0.40, 0.80),
            ("transient_mix", 0.10, 0.30),
        ),
    ),
    "closed_hat": DrumFamilySpec(
        6,
        0.06,
        0.30,
        ("TICK", "METAL", "CRISP", "THIN", "DARK", "GRAIN"),
        (
            ("base_frequency_hz", 4_000.0, 8_000.0),
            ("decay", 18.0, 45.0),
            ("metallic_mix", 0.35, 0.70),
        ),
    ),
    "open_hat": DrumFamilySpec(
        4,
        0.30,
        1.15,
        ("AIR", "METAL", "WASH", "TAIL"),
        (
            ("base_frequency_hz", 4_000.0, 8_000.0),
            ("decay", 4.0, 9.0),
            ("metallic_mix", 0.35, 0.70),
        ),
    ),
    "shaker": DrumFamilySpec(
        6,
        0.12,
        0.50,
        ("FINE", "COARSE", "WOOD", "DUST", "MESH", "PULSE"),
        (
            ("event_count", 7.0, 20.0),
            ("grain_decay", 100.0, 225.0),
        ),
    ),
    "percussion": DrumFamilySpec(
        8,
        0.14,
        1.00,
        ("TONAL", "METAL", "WOOD", "MEMBRANE", "SYNTH", "CLAVE", "BELL", "IMPACT"),
        (
            ("decay", 5.0, 30.0),
            ("fundamental_hz", 150.0, 610.0),
            ("noise_mix", 0.04, 0.25),
        ),
    ),
}
DRUM_FAMILIES = tuple(DRUM_FAMILY_SPECS)
DRUM_SOURCE_COUNT = sum(spec.count for spec in DRUM_FAMILY_SPECS.values())
PREVIEW_DURATION_BOUNDS = (3.0, 12.0)


@dataclass(frozen=True)
class DrumStyleProfile:
    """Objective synthesis tendencies for an original Abletools style profile."""

    style: str
    brightness: float
    transient_sharpness: float
    saturation: float
    asymmetry: float
    tail_scale: float
    target_peak: float
    description: str


DRUM_STYLE_PROFILES: dict[str, DrumStyleProfile] = {
    "DRUIID": DrumStyleProfile(
        style="DRUIID",
        brightness=0.78,
        transient_sharpness=0.82,
        saturation=0.18,
        asymmetry=0.08,
        tail_scale=0.82,
        target_peak=0.84,
        description="precise geometric transients with controlled low end and hybrid detail",
    ),
    "HAZY": DrumStyleProfile(
        style="HAZY",
        brightness=0.34,
        transient_sharpness=0.38,
        saturation=0.42,
        asymmetry=0.32,
        tail_scale=1.12,
        target_peak=0.80,
        description="softened dusty edges, filtered noise, restrained wear, and bounded tails",
    ),
}


@dataclass(frozen=True)
class DrumEssentialsRecipe:
    """Canonical pack controls with family-isolated character namespaces."""

    seed: int
    style: str
    kick_character: float = 0.5
    snare_character: float = 0.5
    hat_character: float = 0.5
    shaker_character: float = 0.5
    percussion_character: float = 0.5
    sample_rate: int = SAMPLE_RATE
    bit_depth: int = BIT_DEPTH
    channels: int = CHANNELS

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed <= 9999:
            raise ValueError("seed must be an integer from 0 to 9999")
        if self.style not in DRUM_STYLE_PROFILES:
            raise ValueError("style must be DRUIID or HAZY")
        if (self.sample_rate, self.bit_depth, self.channels) != (SAMPLE_RATE, BIT_DEPTH, CHANNELS):
            raise ValueError("Drum Essentials requires mono 48 kHz, 24-bit PCM")
        for name in (
            "kick_character",
            "snare_character",
            "hat_character",
            "shaker_character",
            "percussion_character",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")
            object.__setattr__(self, name, float(value))
        require_capability(f"{self.style.lower()}_drum_one_shot_essentials")

    @property
    def profile(self) -> DrumStyleProfile:
        return DRUM_STYLE_PROFILES[self.style]

    @property
    def profile_version(self) -> str:
        return PROFILE_VERSIONS[self.style]

    def character_for(self, family: str) -> float:
        try:
            field = {
                "kick": "kick_character",
                "snare": "snare_character",
                "closed_hat": "hat_character",
                "open_hat": "hat_character",
                "shaker": "shaker_character",
                "percussion": "percussion_character",
            }[family]
        except KeyError as error:
            raise ValueError(f"unknown drum family: {family}") from error
        return getattr(self, field)

    def canonical_data(self) -> dict[str, Any]:
        return {
            "bit_depth": self.bit_depth,
            "channels": self.channels,
            "hat_character": self.hat_character,
            "kick_character": self.kick_character,
            "percussion_character": self.percussion_character,
            "sample_rate": self.sample_rate,
            "seed": self.seed,
            "shaker_character": self.shaker_character,
            "snare_character": self.snare_character,
            "style": self.style,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.canonical_data())

    def family_seed_data(self, family: str) -> dict[str, Any]:
        """Return only identity and controls allowed to affect one family."""
        if family not in DRUM_FAMILY_SPECS:
            raise ValueError(f"unknown drum family: {family}")
        return {
            "character": self.character_for(family),
            "profile": self.profile_version,
            "sample_rate": self.sample_rate,
            "seed": self.seed,
            "style": self.style,
        }


@dataclass(frozen=True)
class DrumVoiceRecipe:
    """One reconstructible family/variant render request."""

    pack: DrumEssentialsRecipe
    family: str
    variant: int

    def __post_init__(self) -> None:
        if self.family not in DRUM_FAMILY_SPECS:
            raise ValueError(f"unknown drum family: {self.family}")
        if isinstance(self.variant, bool) or not isinstance(self.variant, int):
            raise ValueError("variant must be an integer")
        if not 1 <= self.variant <= DRUM_FAMILY_SPECS[self.family].count:
            raise ValueError(f"variant is outside the {self.family} catalog")

    @property
    def descriptor(self) -> str:
        return DRUM_FAMILY_SPECS[self.family].descriptors[self.variant - 1]

    def seed_data(self) -> dict[str, Any]:
        return {
            **self.pack.family_seed_data(self.family),
            "descriptor": self.descriptor,
            "family": self.family,
            "variant": self.variant,
        }


def drum_filename(recipe: DrumVoiceRecipe) -> str:
    family = recipe.family.upper()
    return (
        f"{recipe.pack.style}_{family}_{recipe.descriptor}_S{recipe.pack.seed:04d}_"
        f"V{recipe.variant:02d}.wav"
    )


def drum_relative_path(recipe: DrumVoiceRecipe) -> str:
    return f"WAV/{recipe.family.upper()}/{drum_filename(recipe)}"


def preview_relative_path(recipe: DrumEssentialsRecipe) -> str:
    return f"PREVIEWS/{recipe.style}_DRUM_ESSENTIALS_PREVIEW_S{recipe.seed:04d}_V01.wav"
