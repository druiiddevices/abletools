"""Provisional DRUIID musical-behavior generators for MIDI Essentials."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Mapping

from .midi import BEATS_PER_BAR, PPQ, MidiNote
from .recipe import MidiEssentialsRecipe, SCALES
from .seed import seeded_rng

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
PRACTICAL_RANGES = {
    "chords": (48, 84),
    "bass": (28, 52),
    "motif": (60, 88),
}
GM_DRUM_MAPPING = {
    "kick": 36,
    "snare": 38,
    "closed_hat": 42,
    "open_hat": 46,
    "low_percussion": 47,
    "high_percussion": 50,
}
VARIATION_RELATIONSHIPS = {
    "A": "foundation",
    "B": "restrained mutation of A",
    "C": "stronger bounded mutation of A",
}


@dataclass(frozen=True)
class GeneratedMidiAsset:
    """Notes and complete manifest metadata for one generated clip."""

    role: str
    descriptor: str
    variation: str
    notes: tuple[MidiNote, ...]
    note_range: tuple[int, int] | None
    metadata: dict[str, Any]
    drum_mapping: Mapping[str, int] | None = None
    expected_channel: int | None = 0


def _root_pc(recipe: MidiEssentialsRecipe) -> int:
    return NOTE_NAMES.index(recipe.root)


def _scale_pitch(recipe: MidiEssentialsRecipe, degree: int, octave: int) -> int:
    zero_based = degree - 1
    scale_octave, index = divmod(zero_based, 7)
    return (octave + 1 + scale_octave) * 12 + _root_pc(recipe) + SCALES[recipe.scale][index]


def _degree_pitch_class(recipe: MidiEssentialsRecipe, degree: int) -> int:
    return _scale_pitch(recipe, degree, 0) % 12


def _nearest_pitch(pitch_class: int, low: int, high: int, target: int) -> int:
    candidates = [note for note in range(low, high + 1) if note % 12 == pitch_class]
    if not candidates:
        raise ValueError("pitch class is absent from the requested practical range")
    return min(candidates, key=lambda note: (abs(note - target), note))


def _triad_pitch_classes(recipe: MidiEssentialsRecipe, degree: int) -> tuple[int, int, int]:
    return tuple(_degree_pitch_class(recipe, degree + offset) for offset in (0, 2, 4))


def _triad_symbol(recipe: MidiEssentialsRecipe, degree: int) -> str:
    pitches = [_scale_pitch(recipe, degree + offset, 3) for offset in (0, 2, 4)]
    root = pitches[0]
    intervals = (0, (pitches[1] - root) % 12, (pitches[2] - root) % 12)
    quality = {
        (0, 4, 7): "",
        (0, 3, 7): "m",
        (0, 3, 6): "dim",
        (0, 4, 8): "aug",
    }.get(intervals, f"({intervals[1]},{intervals[2]})")
    return f"{NOTE_NAMES[root % 12]}{quality}"


def _voice_triad(
    pitch_classes: tuple[int, int, int],
    previous: tuple[int, int, int] | None,
    target_center: int,
) -> tuple[int, int, int]:
    low, high = PRACTICAL_RANGES["chords"]
    candidates_by_voice = [
        [note for note in range(low, high + 1) if note % 12 == pitch_class]
        for pitch_class in pitch_classes
    ]
    candidates: list[tuple[int, int, int]] = []
    for raw in itertools.product(*candidates_by_voice):
        voiced = tuple(sorted(raw))
        if len(set(voiced)) == 3 and voiced[-1] - voiced[0] <= 24:
            candidates.append(voiced)
    if not candidates:
        raise ValueError("unable to voice chord inside the practical range")
    if previous is None:
        return min(
            candidates,
            key=lambda chord: (abs(sum(chord) / 3 - target_center), chord[-1] - chord[0], chord),
        )
    return min(
        candidates,
        key=lambda chord: (
            sum(abs(note - prior) for note, prior in zip(chord, previous)),
            abs(sum(chord) / 3 - target_center),
            chord[-1] - chord[0],
            chord,
        ),
    )


def _base_metadata(
    recipe: MidiEssentialsRecipe,
    role: str,
    variation: str,
    mutation_amount: float,
) -> dict[str, Any]:
    return {
        "bars": recipe.bars,
        "key": recipe.key,
        "meter": "4/4",
        "mutation_amount": mutation_amount,
        "non_deterministic_stage": None,
        "profile_version": recipe.profile_version,
        "role": role,
        "root": recipe.root,
        "scale": recipe.scale,
        "seed": recipe.seed,
        "tempo_bpm": recipe.bpm,
        "variation": variation,
        "variation_relationship": VARIATION_RELATIONSHIPS[variation],
    }


def generate_chords(recipe: MidiEssentialsRecipe, variation: str) -> GeneratedMidiAsset:
    """Generate degree-first triads with smooth voice leading and bounded inversions."""
    mutation = recipe.mutation_for("chords", variation)
    base_rng = seeded_rng(recipe.seed, "druiid-chords-base", recipe.base_seed_data())
    mutation_rng = seeded_rng(
        recipe.seed,
        "druiid-chords-mutation",
        {"recipe": recipe.role_seed_data("chords"), "variation": variation},
    )
    target_center = 62 + base_rng.choice((-2, 0, 2))
    voicings: list[tuple[int, int, int]] = []
    previous: tuple[int, int, int] | None = None
    for degree in recipe.progression:
        previous = _voice_triad(_triad_pitch_classes(recipe, degree), previous, target_center)
        voicings.append(previous)

    if mutation > 0:
        change_count = 1 if variation == "B" else min(2, len(voicings))
        for index in mutation_rng.sample(range(len(voicings)), k=change_count):
            voiced = list(voicings[index])
            if voiced[0] + 12 <= PRACTICAL_RANGES["chords"][1]:
                voiced[0] += 12
            else:
                voiced[-1] -= 12
            voicings[index] = tuple(sorted(voiced))

    total_ticks = recipe.bars * BEATS_PER_BAR * PPQ
    chord_ticks = total_ticks // len(recipe.progression)
    notes: list[MidiNote] = []
    max_strum = round(recipe.humanize_ticks * mutation)
    for chord_index, voiced in enumerate(voicings):
        chord_start = chord_index * chord_ticks
        for voice, pitch in enumerate(voiced):
            strum = voice * mutation_rng.randint(0, max_strum) if max_strum else 0
            duration = chord_ticks - strum - 24
            velocity = 78 - voice * 4 + (4 if chord_index in (0, len(voicings) - 1) else 0)
            notes.append(MidiNote(chord_start + strum, duration, pitch, velocity))

    metadata = _base_metadata(recipe, "chords", variation, mutation)
    metadata.update(
        {
            "chord_symbols": [_triad_symbol(recipe, degree) for degree in recipe.progression],
            "degree_sequence": list(recipe.progression),
            "note_range": list(PRACTICAL_RANGES["chords"]),
            "upper_voice_lock": True,
        }
    )
    return GeneratedMidiAsset(
        "chords",
        "CHORDS",
        variation,
        tuple(notes),
        PRACTICAL_RANGES["chords"],
        metadata,
    )


def generate_bass(recipe: MidiEssentialsRecipe, variation: str) -> GeneratedMidiAsset:
    """Generate a separately mutable low-register progression part."""
    mutation = recipe.mutation_for("bass", variation)
    rng = seeded_rng(
        recipe.seed,
        "druiid-bass",
        {"recipe": recipe.role_seed_data("bass"), "variation": variation},
    )
    notes: list[MidiNote] = []
    bar_ticks = BEATS_PER_BAR * PPQ
    low, high = PRACTICAL_RANGES["bass"]
    for bar in range(recipe.bars):
        degree = recipe.progression[bar % len(recipe.progression)]
        root = _nearest_pitch(_degree_pitch_class(recipe, degree), low, high, 40)
        velocity = 88 + (4 if bar % len(recipe.progression) == 0 else 0)
        notes.append(MidiNote(bar * bar_ticks, PPQ + PPQ // 2, root, velocity))
        if mutation > 0 and (variation == "C" or bar % 2 == rng.randrange(2)):
            fifth = _nearest_pitch(_degree_pitch_class(recipe, degree + 4), low, high, root + 5)
            notes.append(MidiNote(bar * bar_ticks + 2 * PPQ, PPQ // 2, fifth, 72))
        if variation == "C" and mutation >= 0.25 and bar % 2 == 1:
            next_degree = recipe.progression[(bar + 1) % len(recipe.progression)]
            connector = _nearest_pitch(_degree_pitch_class(recipe, next_degree), low, high, root)
            notes.append(MidiNote(bar * bar_ticks + 7 * PPQ // 2, PPQ // 3, connector, 68))

    metadata = _base_metadata(recipe, "bass", variation, mutation)
    metadata.update(
        {
            "degree_sequence": list(recipe.progression),
            "note_range": list(PRACTICAL_RANGES["bass"]),
            "relationship": "bass mutation is independent from upper-voice mutation",
        }
    )
    return GeneratedMidiAsset(
        "bass",
        "BASS",
        variation,
        tuple(notes),
        PRACTICAL_RANGES["bass"],
        metadata,
    )


def generate_motif(recipe: MidiEssentialsRecipe, variation: str) -> GeneratedMidiAsset:
    """Generate a short scale-degree cell with anchored, bounded mutation."""
    mutation = recipe.mutation_for("motif", variation)
    base_rng = seeded_rng(recipe.seed, "druiid-motif-base", recipe.base_seed_data())
    rng = seeded_rng(
        recipe.seed,
        "druiid-motif-mutation",
        {"recipe": recipe.role_seed_data("motif"), "variation": variation},
    )
    cells = ((1, 3, 2, 5), (1, 2, 4, 3), (1, 4, 3, 5))
    base_cell = list(base_rng.choice(cells))
    notes: list[MidiNote] = []
    bar_ticks = BEATS_PER_BAR * PPQ
    low, high = PRACTICAL_RANGES["motif"]
    for bar in range(recipe.bars):
        cell = base_cell.copy()
        if mutation > 0 and bar % 2 == 1:
            index = rng.choice((1, 2, 3))
            direction = rng.choice((-1, 1))
            cell[index] = max(1, min(7, cell[index] + direction))
        if variation == "C" and mutation >= 0.25 and bar == recipe.bars - 1:
            cell[-1] = 1
        chord_degree = recipe.progression[bar % len(recipe.progression)]
        for step, cell_degree in enumerate(cell):
            absolute_degree = ((chord_degree + cell_degree - 2) % 7) + 1
            pitch = _nearest_pitch(_degree_pitch_class(recipe, absolute_degree), low, high, 72)
            jitter_limit = round(recipe.humanize_ticks * mutation)
            jitter = rng.randint(-jitter_limit, jitter_limit) if jitter_limit and step else 0
            start = bar * bar_ticks + step * PPQ + jitter
            velocity = 76 + (8 if step == 0 else 0) - step * 2
            notes.append(MidiNote(start, 3 * PPQ // 4, pitch, velocity))

    metadata = _base_metadata(recipe, "motif", variation, mutation)
    metadata.update(
        {
            "anchor": "downbeat rhythm and first cell degree",
            "motif_degree_cell": base_cell,
            "note_range": list(PRACTICAL_RANGES["motif"]),
        }
    )
    return GeneratedMidiAsset(
        "motif",
        "MOTIF",
        variation,
        tuple(notes),
        PRACTICAL_RANGES["motif"],
        metadata,
    )


def generate_drums(recipe: MidiEssentialsRecipe, variation: str) -> GeneratedMidiAsset:
    """Generate a stable GM-mapped pulse with bounded role-specific mutations."""
    mutation = recipe.mutation_for("drums", variation)
    rng = seeded_rng(
        recipe.seed,
        "druiid-drums",
        {"recipe": recipe.role_seed_data("drums"), "variation": variation},
    )
    notes: list[MidiNote] = []
    bar_ticks = BEATS_PER_BAR * PPQ
    jitter_limit = round(recipe.humanize_ticks * mutation)
    for bar in range(recipe.bars):
        bar_start = bar * bar_ticks
        for beat in (0, 2):
            start = bar_start + beat * PPQ
            notes.append(MidiNote(start, PPQ // 8, GM_DRUM_MAPPING["kick"], 102, channel=9))
        for beat in (1, 3):
            jitter = rng.randint(-jitter_limit, jitter_limit) if jitter_limit else 0
            start = bar_start + beat * PPQ + jitter
            notes.append(MidiNote(start, PPQ // 8, GM_DRUM_MAPPING["snare"], 94, channel=9))
        for eighth in range(8):
            jitter = rng.randint(-jitter_limit, jitter_limit) if jitter_limit and eighth else 0
            start = bar_start + eighth * PPQ // 2 + jitter
            velocity = 66 if eighth % 2 == 0 else 54
            notes.append(MidiNote(start, PPQ // 10, GM_DRUM_MAPPING["closed_hat"], velocity, channel=9))
        if mutation > 0 and bar % 2 == rng.randrange(2):
            notes.append(
                MidiNote(bar_start + 3 * PPQ // 2, PPQ // 8, GM_DRUM_MAPPING["kick"], 84, channel=9)
            )
        if variation == "C" and mutation >= 0.25:
            percussion = "low_percussion" if bar % 2 == 0 else "high_percussion"
            notes.append(
                MidiNote(bar_start + 7 * PPQ // 2, PPQ // 8, GM_DRUM_MAPPING[percussion], 70, channel=9)
            )
            if bar % 4 == 3:
                notes.append(
                    MidiNote(bar_start + 3 * PPQ, PPQ // 6, GM_DRUM_MAPPING["open_hat"], 72, channel=9)
                )

    metadata = _base_metadata(recipe, "drum_pattern", variation, mutation)
    metadata.update(
        {
            "channel": 10,
            "drum_mapping": dict(GM_DRUM_MAPPING),
            "pulse_lock": "kick downbeats remain fixed; secondary roles receive bounded offsets",
        }
    )
    return GeneratedMidiAsset(
        "drum_pattern",
        "DRUMS",
        variation,
        tuple(notes),
        None,
        metadata,
        GM_DRUM_MAPPING,
        9,
    )


def generate_midi_essentials(recipe: MidiEssentialsRecipe) -> list[GeneratedMidiAsset]:
    """Generate related A/B/C forms for every MIDI Essentials role."""
    assets: list[GeneratedMidiAsset] = []
    for variation in ("A", "B", "C"):
        assets.extend(
            (
                generate_chords(recipe, variation),
                generate_bass(recipe, variation),
                generate_motif(recipe, variation),
                generate_drums(recipe, variation),
            )
        )
    return assets
