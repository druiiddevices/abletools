"""Original HAZY musical generators for the MIDI Essentials milestone."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Mapping

from .midi import BEATS_PER_BAR, PPQ, MidiNote
from .recipe import HAZY_MODES, HazyMidiRecipe
from .seed import seeded_rng

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
PRACTICAL_RANGES = {
    "chords": (45, 86),
    "bass": (28, 52),
    "motif": (60, 84),
    "arpeggio": (52, 86),
}
HAZY_GM_DRUM_MAPPING = {
    "kick": 36,
    "snare": 38,
    "closed_hat": 42,
    "open_hat": 46,
    "low_percussion": 47,
    "high_percussion": 50,
}
VARIATION_RELATIONSHIPS = {
    "A": "foundation: stable identity and the clearest pulse",
    "B": "related variation: one restrained voicing, rotation, register, or timing mutation",
    "C": "related variation: one stronger bounded color, cadence, displacement, or pedal mutation",
}


@dataclass(frozen=True)
class GeneratedHazyMidiAsset:
    """Notes and complete manifest metadata for one HAZY clip."""

    role: str
    descriptor: str
    variation: str
    notes: tuple[MidiNote, ...]
    note_range: tuple[int, int] | None
    metadata: dict[str, Any]
    drum_mapping: Mapping[str, int] | None = None
    expected_channel: int | None = 0


def _root_pc(recipe: HazyMidiRecipe) -> int:
    return NOTE_NAMES.index(recipe.root)


def _scale_pitch(recipe: HazyMidiRecipe, degree: int, octave: int) -> int:
    zero_based = degree - 1
    scale_octave, index = divmod(zero_based, 7)
    return (octave + 1 + scale_octave) * 12 + _root_pc(recipe) + HAZY_MODES[recipe.mode][index]


def _degree_pc(recipe: HazyMidiRecipe, degree: int) -> int:
    return _scale_pitch(recipe, degree, 0) % 12


def _allowed_pitch_classes(recipe: HazyMidiRecipe) -> set[int]:
    root = _root_pc(recipe)
    return {(root + interval) % 12 for interval in HAZY_MODES[recipe.mode]}


def _nearest_pitch(pitch_class: int, low: int, high: int, target: int) -> int:
    candidates = [pitch for pitch in range(low, high + 1) if pitch % 12 == pitch_class]
    if not candidates:
        raise ValueError("pitch class is absent from the requested practical range")
    return min(candidates, key=lambda pitch: (abs(pitch - target), pitch))


def _triad_pcs(recipe: HazyMidiRecipe, degree: int) -> tuple[int, int, int]:
    return tuple(_degree_pc(recipe, degree + offset) for offset in (0, 2, 4))


def _triad_quality(recipe: HazyMidiRecipe, degree: int) -> str:
    pitches = [_scale_pitch(recipe, degree + offset, 3) for offset in (0, 2, 4)]
    intervals = (0, (pitches[1] - pitches[0]) % 12, (pitches[2] - pitches[0]) % 12)
    return {
        (0, 4, 7): "",
        (0, 3, 7): "m",
        (0, 3, 6): "dim",
        (0, 4, 8): "aug",
    }.get(intervals, f"({intervals[1]},{intervals[2]})")


def _harmony_plan(
    recipe: HazyMidiRecipe, variation: str
) -> list[tuple[tuple[int, ...], str, str]]:
    """Return pitch classes, symbols, and deliberately restrained color labels."""
    mutation = recipe.mutation_for("chords", variation)
    plan: list[tuple[tuple[int, ...], str, str]] = []
    for index, degree in enumerate(recipe.progression):
        root_pc, third_pc, fifth_pc = _triad_pcs(recipe, degree)
        color = "triad"
        pcs: tuple[int, ...] = (root_pc, third_pc, fifth_pc)
        if index % 4 == 0 and recipe.color_amount >= 0.25:
            color = "add2"
            pcs = (root_pc, third_pc, fifth_pc, _degree_pc(recipe, degree + 1))
        elif index % 4 == 2 and recipe.color_amount >= 0.5:
            color = "add6"
            pcs = (root_pc, third_pc, fifth_pc, _degree_pc(recipe, degree + 5))
        elif index % 4 == 3 and recipe.ambiguity >= 0.45:
            color = "sus2"
            pcs = (root_pc, _degree_pc(recipe, degree + 1), fifth_pc)

        if variation == "B" and mutation > 0 and index % 4 == 2:
            color = "7"
            pcs = (root_pc, third_pc, fifth_pc, _degree_pc(recipe, degree + 6))
        elif variation == "C" and mutation > 0 and index % 4 == 1:
            color = "open5"
            pcs = (root_pc, fifth_pc)
        elif variation == "C" and mutation > 0 and index % 4 == 3:
            color = "sus4"
            pcs = (root_pc, _degree_pc(recipe, degree + 3), fifth_pc)

        pcs = tuple(dict.fromkeys(pcs))
        suffix = {
            "triad": _triad_quality(recipe, degree),
            "add2": f"{_triad_quality(recipe, degree)}(add2)",
            "add6": f"{_triad_quality(recipe, degree)}(add6)",
            "7": f"{_triad_quality(recipe, degree)}7",
            "sus2": "sus2",
            "sus4": "sus4",
            "open5": "5(no3)",
        }[color]
        plan.append((pcs, f"{NOTE_NAMES[root_pc]}{suffix}", color))
    return plan


def _voice_pitch_classes(
    pitch_classes: tuple[int, ...],
    previous: tuple[int, ...] | None,
    *,
    forced_note: int | None,
    target_center: int,
    common_tone_preference: float,
) -> tuple[int, ...]:
    low, high = PRACTICAL_RANGES["chords"]
    forced_pc = forced_note % 12 if forced_note is not None else None
    remaining = tuple(pc for pc in pitch_classes if pc != forced_pc)
    candidates_by_pc = [
        [pitch for pitch in range(low, high + 1) if pitch % 12 == pitch_class]
        for pitch_class in remaining
    ]
    raw_candidates = itertools.product(*candidates_by_pc) if candidates_by_pc else [()]
    candidates: list[tuple[int, ...]] = []
    for raw in raw_candidates:
        voiced = tuple(sorted((*raw, *((forced_note,) if forced_note is not None else ()))))
        if len(set(voiced)) != len(voiced) or len(voiced) < 2:
            continue
        span = voiced[-1] - voiced[0]
        if 12 <= span <= 30:
            candidates.append(voiced)
    if not candidates:
        raise ValueError("unable to voice HAZY chord inside the practical range")

    def score(voiced: tuple[int, ...]) -> tuple[float, ...]:
        center_cost = abs(sum(voiced) / len(voiced) - target_center)
        spacing_cost = abs((voiced[-1] - voiced[0]) - 19)
        if previous is None:
            return (center_cost, spacing_cost, *voiced)
        movement = sum(min(abs(note - prior) for prior in previous) for note in voiced)
        common_pcs = len({note % 12 for note in voiced} & {note % 12 for note in previous})
        common_credit = common_pcs * common_tone_preference * 8
        return (movement - common_credit, center_cost, spacing_cost, *voiced)

    return min(candidates, key=score)


def _borrowed_tones(
    recipe: HazyMidiRecipe, notes: list[MidiNote], reason: str
) -> list[dict[str, Any]]:
    allowed = _allowed_pitch_classes(recipe)
    return [
        {
            "midi_note": pitch,
            "pitch_class": NOTE_NAMES[pitch % 12],
            "reason": reason,
        }
        for pitch in sorted({note.note for note in notes if note.note % 12 not in allowed})
    ]


def _base_metadata(
    recipe: HazyMidiRecipe,
    role: str,
    variation: str,
    mutation_amount: float,
    *,
    chord_symbols: list[str] | None = None,
) -> dict[str, Any]:
    symbols = chord_symbols or [symbol for _pcs, symbol, _color in _harmony_plan(recipe, variation)]
    return {
        "bars": recipe.bars,
        "chord_symbols": symbols,
        "degree_sequence": list(recipe.progression),
        "harmonic_archetype": recipe.harmonic_archetype,
        "key": recipe.key,
        "meter": "4/4",
        "mode": recipe.mode,
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


def _voice_leading_metadata(voicings: list[tuple[int, ...]]) -> dict[str, Any]:
    movements: list[int] = []
    exact_common: list[int] = []
    pitch_class_common: list[int] = []
    for previous, current in zip(voicings, voicings[1:]):
        movements.append(sum(min(abs(note - prior) for prior in previous) for note in current))
        exact_common.append(len(set(previous) & set(current)))
        pitch_class_common.append(
            len({note % 12 for note in previous} & {note % 12 for note in current})
        )
    return {
        "exact_common_tone_counts": exact_common,
        "max_transition_movement": max(movements, default=0),
        "pitch_class_common_tone_counts": pitch_class_common,
        "total_transition_movement": sum(movements),
        "transition_movements": movements,
    }


def generate_hazy_chords(recipe: HazyMidiRecipe, variation: str) -> GeneratedHazyMidiAsset:
    """Generate modal, open-spaced harmony with declared pedal and tension behavior."""
    mutation = recipe.mutation_for("chords", variation)
    rng = seeded_rng(
        recipe.seed,
        "hazy-chords",
        {"recipe": recipe.role_seed_data("chords"), "variation": variation},
    )
    plan = _harmony_plan(recipe, variation)
    pedal_note = _nearest_pitch(_root_pc(recipe), *PRACTICAL_RANGES["chords"], 50)
    pedal_indices = [
        index
        for index in range(len(plan))
        if recipe.pedal_preference >= 0.5 and index % 4 != 1
    ]
    target_center = 64 + {"A": 0, "B": 3, "C": -2}[variation]
    voicings: list[tuple[int, ...]] = []
    previous: tuple[int, ...] | None = None
    for index, (pitch_classes, _symbol, _color) in enumerate(plan):
        previous = _voice_pitch_classes(
            pitch_classes,
            previous,
            forced_note=pedal_note if index in pedal_indices else None,
            target_center=target_center,
            common_tone_preference=recipe.common_tone_preference,
        )
        voicings.append(previous)

    total_ticks = recipe.bars * BEATS_PER_BAR * PPQ
    chord_ticks = total_ticks // len(recipe.progression)
    notes: list[MidiNote] = []
    max_strum = round(recipe.groove_drift * mutation)
    for chord_index, voiced in enumerate(voicings):
        chord_start = chord_index * chord_ticks
        for voice, pitch in enumerate(voiced):
            strum = rng.randint(0, max_strum) * voice if max_strum else 0
            duration = chord_ticks - strum - 36
            velocity = 70 + (5 if voice == len(voiced) - 1 else 0) - min(voice, 3) * 2
            notes.append(MidiNote(chord_start + strum, duration, pitch, velocity))

    tension_event: dict[str, Any] | None = None
    if variation == "C" and recipe.tension >= 0.25:
        chord_index = min(1, len(voicings) - 1)
        chromatic_pc = _chromatic_approach_pc(
            recipe, _degree_pc(recipe, recipe.progression[chord_index])
        )
        tension_note = _nearest_pitch(
            chromatic_pc,
            voicings[chord_index][0] + 1,
            voicings[chord_index][-1] - 1,
            sum(voicings[chord_index]) // len(voicings[chord_index]),
        )
        tension_start = chord_index * chord_ticks + chord_ticks // 2
        tension_duration = min(PPQ // 2, chord_ticks // 4)
        notes.append(MidiNote(tension_start, tension_duration, tension_note, 58))
        tension_event = {
            "chord_index": chord_index,
            "midi_note": tension_note,
            "resolution": "short inner-voice neighbor releases inside the same harmony",
        }

    metadata = _base_metadata(
        recipe,
        "chords",
        variation,
        mutation,
        chord_symbols=[symbol for _pcs, symbol, _color in plan],
    )
    metadata.update(
        {
            "borrowed_tones": _borrowed_tones(
                recipe, notes, "declared chromatic inner-voice tension"
            ),
            "color_behavior": [color for _pcs, _symbol, color in plan],
            "common_tone_behavior": "voicings minimize movement and credit retained pitch classes",
            "note_range": list(PRACTICAL_RANGES["chords"]),
            "pedal": {
                "chord_indices": pedal_indices,
                "enabled": bool(pedal_indices),
                "midi_note": pedal_note if pedal_indices else None,
                "pitch_class": NOTE_NAMES[pedal_note % 12] if pedal_indices else None,
            },
            "tension_event": tension_event,
            "timing_model": {
                "chord_ticks": chord_ticks,
                "maximum_voice_strum_ticks": max_strum * max((len(v) - 1 for v in voicings), default=0),
                "strategy": "bounded per-voice onset spread; harmonic boundaries remain fixed",
            },
            "voice_leading": _voice_leading_metadata(voicings),
            "voicing_or_color_behavior": "open spacing, retained tones, inversions, selective pedal, and restrained color",
            "voicings": [list(voicing) for voicing in voicings],
        }
    )
    return GeneratedHazyMidiAsset(
        "chords",
        "CHORDS",
        variation,
        tuple(notes),
        PRACTICAL_RANGES["chords"],
        metadata,
    )


def _chromatic_approach_pc(recipe: HazyMidiRecipe, target_pc: int) -> int:
    allowed = _allowed_pitch_classes(recipe)
    for offset in (-1, 1, -2, 2):
        candidate = (target_pc + offset) % 12
        if candidate not in allowed:
            return candidate
    raise ValueError("unable to derive an out-of-mode approach pitch")


def generate_hazy_bass(recipe: HazyMidiRecipe, variation: str) -> GeneratedHazyMidiAsset:
    """Generate low roots, fifths, pedals, octave shifts, and sparing approaches."""
    mutation = recipe.mutation_for("bass", variation)
    rng = seeded_rng(
        recipe.seed,
        "hazy-bass",
        {"recipe": recipe.role_seed_data("bass"), "variation": variation},
    )
    low, high = PRACTICAL_RANGES["bass"]
    bar_ticks = BEATS_PER_BAR * PPQ
    pedal_note = _nearest_pitch(_root_pc(recipe), low, high, 38)
    notes: list[MidiNote] = []
    octave_displacements: list[int] = []
    for bar in range(recipe.bars):
        degree = recipe.progression[bar % len(recipe.progression)]
        root_note = _nearest_pitch(_degree_pc(recipe, degree), low, high, 38)
        displacement = 0
        if variation in {"B", "C"} and mutation > 0 and bar % 2 == 1:
            displacement = 12 if root_note + 12 <= high else -12
            root_note += displacement
        octave_displacements.append(displacement)
        notes.append(MidiNote(bar * bar_ticks, 3 * PPQ // 2, root_note, 86 + (bar == 0) * 4))
        if recipe.pedal_preference >= 0.5 and bar % 2 == 0:
            notes.append(MidiNote(bar * bar_ticks + 2 * PPQ, PPQ // 2, pedal_note, 68))
        if variation in {"B", "C"} and mutation > 0:
            fifth_note = _nearest_pitch(_degree_pc(recipe, degree + 4), low, high, root_note + 5)
            notes.append(MidiNote(bar * bar_ticks + 11 * PPQ // 4, PPQ // 2, fifth_note, 72))
        if variation == "C" and mutation > 0 and bar % 2 == rng.randrange(2):
            next_degree = recipe.progression[(bar + 1) % len(recipe.progression)]
            target_pc = _degree_pc(recipe, next_degree)
            approach_pc = _chromatic_approach_pc(recipe, target_pc)
            approach_note = _nearest_pitch(approach_pc, low, high, 38)
            notes.append(MidiNote(bar * bar_ticks + 7 * PPQ // 2, PPQ // 3, approach_note, 61))

    metadata = _base_metadata(recipe, "bass", variation, mutation)
    metadata.update(
        {
            "bass_behavior": "low-register roots with selective tonic pedal, fifth support, and sparse approaches",
            "borrowed_tones": _borrowed_tones(
                recipe, notes, "declared chromatic approach into the next harmonic root"
            ),
            "note_range": list(PRACTICAL_RANGES["bass"]),
            "octave_displacements": octave_displacements,
            "pedal": {
                "bars": [bar for bar in range(recipe.bars) if recipe.pedal_preference >= 0.5 and bar % 2 == 0],
                "midi_note": pedal_note,
                "pitch_class": NOTE_NAMES[pedal_note % 12],
            },
            "timing_model": "stable bar roots; optional fifths at beat 3.75 and approaches at beat 4.5",
            "voicing_or_color_behavior": "root/fifth foundation with octave displacement and a restrained tonic pedal",
        }
    )
    return GeneratedHazyMidiAsset(
        "bass", "BASS", variation, tuple(notes), PRACTICAL_RANGES["bass"], metadata
    )


def generate_hazy_motif(recipe: HazyMidiRecipe, variation: str) -> GeneratedHazyMidiAsset:
    """Generate a short repeated cell with one controlled destabilizing element."""
    mutation = recipe.mutation_for("motif", variation)
    base_rng = seeded_rng(recipe.seed, "hazy-motif-identity", recipe.base_seed_data())
    rng = seeded_rng(
        recipe.seed,
        "hazy-motif-mutation",
        {"recipe": recipe.role_seed_data("motif"), "variation": variation},
    )
    base_cell = list(base_rng.choice(((1, 2, 4, 2), (1, 3, 2, 5), (1, 4, 3, 2))))
    low, high = PRACTICAL_RANGES["motif"]
    bar_ticks = BEATS_PER_BAR * PPQ
    notes: list[MidiNote] = []
    destabilizing_event: dict[str, Any] | None = None
    for bar in range(recipe.bars):
        cell = base_cell.copy()
        if variation == "B" and mutation > 0 and bar % 2 == 1:
            cell = cell[1:] + cell[:1]
        for step, degree in enumerate(cell):
            pitch = _nearest_pitch(_degree_pc(recipe, degree), low, high, 72)
            if variation == "C" and mutation > 0 and bar == recipe.bars // 2 and step == 2:
                chromatic_pc = _chromatic_approach_pc(recipe, pitch % 12)
                pitch = _nearest_pitch(chromatic_pc, low, high, pitch)
                destabilizing_event = {
                    "bar": bar + 1,
                    "midi_note": pitch,
                    "step": step + 1,
                    "type": "single chromatic neighbor",
                }
            if bar == recipe.bars - 1 and step == len(cell) - 1:
                pitch = _nearest_pitch(_root_pc(recipe), low, high, 72)
            drift = 0
            if variation != "A" and mutation > 0 and step in (1, 2):
                limit = max(1, round(recipe.groove_drift * mutation))
                drift = (1 if step == 1 else -1) * rng.randint(1, limit)
            start = bar * bar_ticks + step * PPQ + drift
            notes.append(MidiNote(start, 3 * PPQ // 5, pitch, 78 if step == 0 else 66 + step * 2))

    pitch_span = max(note.note for note in notes) - min(note.note for note in notes)
    metadata = _base_metadata(recipe, "motif", variation, mutation)
    metadata.update(
        {
            "borrowed_tones": _borrowed_tones(
                recipe, notes, "declared single chromatic destabilizing neighbor"
            ),
            "deliberate_ending": {
                "degree": 1,
                "midi_note": notes[-1].note,
                "placement": "final cell step",
            },
            "destabilizing_element": destabilizing_event,
            "limited_range_semitones": pitch_span,
            "motif_degree_cell": base_cell,
            "note_range": list(PRACTICAL_RANGES["motif"]),
            "timing_model": "quarter-note cell grid with bounded push/pull on inner steps only",
            "voicing_or_color_behavior": "restrained modal cell with repetition, limited range, and one declared destabilization",
        }
    )
    return GeneratedHazyMidiAsset(
        "motif", "MOTIF", variation, tuple(notes), PRACTICAL_RANGES["motif"], metadata
    )


def generate_hazy_arpeggio(recipe: HazyMidiRecipe, variation: str) -> GeneratedHazyMidiAsset:
    """Generate a recognizable broken-chord cell with seeded bounded variation."""
    mutation = recipe.mutation_for("arpeggio", variation)
    base_rng = seeded_rng(recipe.seed, "hazy-arpeggio-identity", recipe.base_seed_data())
    rng = seeded_rng(
        recipe.seed,
        "hazy-arpeggio-mutation",
        {"recipe": recipe.role_seed_data("arpeggio"), "variation": variation},
    )
    base_cell = list(base_rng.choice(((0, 1, 2, 1), (0, 2, 1, 2), (1, 0, 2, 0))))
    rotation = {"A": 0, "B": 1, "C": 2}[variation] if mutation > 0 else 0
    cell = base_cell[rotation:] + base_cell[:rotation]
    low, high = PRACTICAL_RANGES["arpeggio"]
    bar_ticks = BEATS_PER_BAR * PPQ
    notes: list[MidiNote] = []
    rest_steps: list[int] = []
    octave_steps: list[int] = []
    for bar in range(recipe.bars):
        degree = recipe.progression[bar % len(recipe.progression)]
        chord_pitches = [
            _nearest_pitch(pc, low, high, 65 + index * 4)
            for index, pc in enumerate(_triad_pcs(recipe, degree))
        ]
        for step in range(8):
            if variation == "B" and mutation > 0 and step == 6:
                rest_steps.append(bar * 8 + step)
                continue
            if variation == "C" and mutation > 0 and step in (2, 7):
                rest_steps.append(bar * 8 + step)
                continue
            pitch = chord_pitches[cell[step % len(cell)]]
            if variation == "C" and mutation > 0 and step == 5:
                shifted = pitch + 12 if pitch + 12 <= high else pitch - 12
                pitch = shifted
                octave_steps.append(bar * 8 + step)
            drift = 0
            if variation != "A" and step % 2 == 1:
                limit = max(1, round(recipe.groove_drift * mutation))
                drift = rng.randint(0, limit)
            notes.append(
                MidiNote(
                    bar * bar_ticks + step * PPQ // 2 + drift,
                    PPQ // 3,
                    pitch,
                    68 + (step % 4 == 0) * 8 - (step % 2) * 4,
                )
            )

    metadata = _base_metadata(recipe, "arpeggio", variation, mutation)
    metadata.update(
        {
            "arpeggio_degree_cell": base_cell,
            "borrowed_tones": _borrowed_tones(recipe, notes, "declared non-modal arpeggio color"),
            "note_range": list(PRACTICAL_RANGES["arpeggio"]),
            "octave_displacement_steps": octave_steps,
            "rest_steps": rest_steps,
            "rotation": rotation,
            "timing_model": "eighth-note broken-chord grid with role-local late offsets",
            "voicing_or_color_behavior": "seeded broken-triad cell with bounded rotation, rests, and octave displacement",
        }
    )
    return GeneratedHazyMidiAsset(
        "arpeggio",
        "RHYTHMIC_HARMONY",
        variation,
        tuple(notes),
        PRACTICAL_RANGES["arpeggio"],
        metadata,
    )


def generate_hazy_drums(recipe: HazyMidiRecipe, variation: str) -> GeneratedHazyMidiAsset:
    """Generate a stable GM pulse with role-based, rather than global, microtiming."""
    mutation = recipe.mutation_for("drums", variation)
    rng = seeded_rng(
        recipe.seed,
        "hazy-drums",
        {"recipe": recipe.role_seed_data("drums"), "variation": variation},
    )
    bar_ticks = BEATS_PER_BAR * PPQ
    drift = round(recipe.groove_drift * mutation)
    snare_late = drift
    hat_early = max(0, drift // 2)
    hat_late = max(0, drift - hat_early)
    percussion_late = drift + (1 if drift else 0)
    ghost_phase = rng.randrange(2)
    notes: list[MidiNote] = []
    for bar in range(recipe.bars):
        bar_start = bar * bar_ticks
        for beat in (0, 2):
            notes.append(
                MidiNote(bar_start + beat * PPQ, PPQ // 8, HAZY_GM_DRUM_MAPPING["kick"], 98, channel=9)
            )
        for beat in (1, 3):
            notes.append(
                MidiNote(
                    bar_start + beat * PPQ + snare_late,
                    PPQ // 8,
                    HAZY_GM_DRUM_MAPPING["snare"],
                    88 if beat == 1 else 93,
                    channel=9,
                )
            )
        for eighth in range(8):
            offset = 0
            if variation != "A" and mutation > 0 and eighth:
                offset = -hat_early if eighth % 2 == 0 else hat_late
            notes.append(
                MidiNote(
                    bar_start + eighth * PPQ // 2 + offset,
                    PPQ // 10,
                    HAZY_GM_DRUM_MAPPING["closed_hat"],
                    62 if eighth % 2 == 0 else 51,
                    channel=9,
                )
            )
        if variation in {"B", "C"} and mutation > 0 and bar % 2 == ghost_phase:
            notes.append(
                MidiNote(
                    bar_start + 7 * PPQ // 2,
                    PPQ // 10,
                    HAZY_GM_DRUM_MAPPING["kick"],
                    67,
                    channel=9,
                )
            )
        if variation == "C" and mutation > 0:
            percussion = "low_percussion" if bar % 2 == 0 else "high_percussion"
            notes.append(
                MidiNote(
                    bar_start + 3 * PPQ // 2 + percussion_late,
                    PPQ // 8,
                    HAZY_GM_DRUM_MAPPING[percussion],
                    64,
                    channel=9,
                )
            )
            if bar % 4 == 3:
                notes.append(
                    MidiNote(
                        bar_start + 7 * PPQ // 2 + hat_late,
                        PPQ // 6,
                        HAZY_GM_DRUM_MAPPING["open_hat"],
                        66,
                        channel=9,
                    )
                )

    metadata = _base_metadata(recipe, "drum_pattern", variation, mutation)
    metadata.update(
        {
            "borrowed_tones": [],
            "channel": 10,
            "drum_mapping": dict(HAZY_GM_DRUM_MAPPING),
            "role_microtiming_ticks": {
                "closed_hat_early": -hat_early,
                "closed_hat_late": hat_late,
                "kick": 0,
                "percussion_late": percussion_late,
                "snare_late": snare_late,
            },
            "timing_model": "kick anchor stays fixed; snare, hats, and percussion receive separate bounded offsets",
            "voicing_or_color_behavior": "stable pulse with role-aware accents and restrained seeded irregularity",
        }
    )
    return GeneratedHazyMidiAsset(
        "drum_pattern",
        "DRUMS",
        variation,
        tuple(notes),
        None,
        metadata,
        HAZY_GM_DRUM_MAPPING,
        9,
    )


def generate_hazy_midi_essentials(recipe: HazyMidiRecipe) -> list[GeneratedHazyMidiAsset]:
    """Generate 15 related A/B/C HAZY clips across five independent roles."""
    assets: list[GeneratedHazyMidiAsset] = []
    for variation in ("A", "B", "C"):
        assets.extend(
            (
                generate_hazy_chords(recipe, variation),
                generate_hazy_bass(recipe, variation),
                generate_hazy_motif(recipe, variation),
                generate_hazy_arpeggio(recipe, variation),
                generate_hazy_drums(recipe, variation),
            )
        )
    return assets
