"""Explicit runtime capability gates for asset generation and validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    """A generator/exporter capability and its runtime availability."""

    name: str
    status: str
    description: str
    gate_reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self.status == "enabled"


CAPABILITIES: dict[str, Capability] = {
    "standard_midi": Capability(
        "standard_midi",
        "enabled",
        "Generate and validate Standard MIDI File clips.",
    ),
    "pcm_wav": Capability(
        "pcm_wav",
        "enabled",
        "Generate and validate PCM WAV audio within the R1 boundary.",
    ),
    "zip_pack": Capability(
        "zip_pack",
        "enabled",
        "Create and validate deterministic Abletools ZIP packs.",
    ),
    "druiid_midi_essentials": Capability(
        "druiid_midi_essentials",
        "enabled",
        "Generate the standards-compliant DRUIID MIDI Essentials pack.",
    ),
    "hazy_midi_essentials": Capability(
        "hazy_midi_essentials",
        "gated",
        "Generate the HAZY MIDI Essentials pack.",
        "Scheduled for a separate profile-backed milestone.",
    ),
    "serum2_preset": Capability(
        "serum2_preset",
        "gated",
        "Serialize native Serum 2 presets.",
        "Requires licensed fixtures and fixture-based round-trip tests.",
    ),
    "ableton_rack": Capability(
        "ableton_rack",
        "gated",
        "Serialize native Ableton .adg/.adv racks.",
        "Requires Ableton fixtures and fixture-based round-trip tests.",
    ),
    "ableton_groove": Capability(
        "ableton_groove",
        "gated",
        "Serialize native Ableton .agr grooves.",
        "Requires Ableton fixtures and fixture-based round-trip tests.",
    ),
    "max_for_live": Capability(
        "max_for_live",
        "gated",
        "Serialize native Max for Live .amxd devices.",
        "Requires Max for Live fixtures and fixture-based round-trip tests.",
    ),
}


def get_capability(name: str) -> Capability:
    """Return a declared capability or fail closed for unknown capabilities."""
    try:
        return CAPABILITIES[name]
    except KeyError as error:
        raise ValueError(f"unknown capability: {name}") from error


def require_capability(name: str) -> Capability:
    """Require an enabled capability before entering its runtime path."""
    capability = get_capability(name)
    if not capability.enabled:
        reason = f" {capability.gate_reason}" if capability.gate_reason else ""
        raise RuntimeError(f"capability is gated: {name}.{reason}")
    return capability
