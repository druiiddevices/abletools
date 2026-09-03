"""Dependency-free Standard MIDI generation and strict validation."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .capabilities import require_capability
from .seed import seeded_rng

PPQ = 480
BEATS_PER_BAR = 4


@dataclass(frozen=True)
class MidiNote:
    """One bounded note event in absolute clip ticks."""

    start: int
    duration: int
    note: int
    velocity: int
    channel: int = 0

    @property
    def end(self) -> int:
        return self.start + self.duration


def _vlq(value: int) -> bytes:
    if value < 0:
        raise ValueError("MIDI delta times cannot be negative")
    buffer = value & 0x7F
    encoded = bytearray([buffer])
    while value >> 7:
        value >>= 7
        buffer = (value & 0x7F) | 0x80
        encoded.insert(0, buffer)
    return bytes(encoded)


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack(">I", len(payload)) + payload


def _event(delta: int, payload: bytes) -> bytes:
    return _vlq(delta) + payload


def write_midi_clip(
    path: str | Path,
    notes: Sequence[MidiNote],
    *,
    bpm: int | float,
    bars: int,
    track_name: str,
) -> Path:
    """Write a deterministic type-0, 4/4 MIDI clip from absolute note events."""
    require_capability("standard_midi")
    if not notes:
        raise ValueError("at least one MIDI note is required")
    if isinstance(bpm, bool) or not isinstance(bpm, (int, float)) or not 0 < bpm <= 1_000:
        raise ValueError("bpm must be greater than zero and no more than 1000")
    if isinstance(bars, bool) or not isinstance(bars, int) or bars <= 0:
        raise ValueError("bars must be a positive integer")
    if not isinstance(track_name, str) or not track_name.strip():
        raise ValueError("track_name must be a non-empty string")

    total_ticks = bars * BEATS_PER_BAR * PPQ
    timed_events: list[tuple[int, int, int, bytes]] = []
    active_intervals: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for index, note in enumerate(notes):
        if isinstance(note.start, bool) or not isinstance(note.start, int) or note.start < 0:
            raise ValueError("MIDI note starts must be non-negative integer ticks")
        if isinstance(note.duration, bool) or not isinstance(note.duration, int) or note.duration <= 0:
            raise ValueError("MIDI notes must have positive integer durations")
        if note.end > total_ticks:
            raise ValueError("MIDI note extends beyond the declared clip length")
        if not 0 <= note.note <= 127:
            raise ValueError("MIDI notes must be from 0 to 127")
        if not 1 <= note.velocity <= 127:
            raise ValueError("MIDI note velocities must be from 1 to 127")
        if not 0 <= note.channel <= 15:
            raise ValueError("MIDI channels must be from 0 to 15")
        key = (note.channel, note.note)
        intervals = active_intervals.setdefault(key, [])
        if any(note.start < end and note.end > start for start, end in intervals):
            raise ValueError("overlapping events for the same MIDI note are not supported")
        intervals.append((note.start, note.end))
        timed_events.append(
            (note.start, 1, index, bytes((0x90 | note.channel, note.note, note.velocity)))
        )
        timed_events.append((note.end, 0, index, bytes((0x80 | note.channel, note.note, 0))))

    timed_events.sort(key=lambda item: (item[0], item[1], item[2]))
    tempo = round(60_000_000 / float(bpm))
    if not 1 <= tempo <= 0xFFFFFF:
        raise ValueError("bpm cannot be represented by the MIDI tempo event")
    name = track_name.strip().encode("utf-8")[:127]
    track = bytearray()
    track += _event(0, b"\xFF\x03" + _vlq(len(name)) + name)
    track += _event(0, b"\xFF\x51\x03" + tempo.to_bytes(3, "big"))
    track += _event(0, b"\xFF\x58\x04\x04\x02\x18\x08")

    last_tick = 0
    for tick, _priority, _index, payload in timed_events:
        track += _event(tick - last_tick, payload)
        last_tick = tick
    track += _event(total_ticks - last_tick, b"\xFF\x2F\x00")

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    header = struct.pack(">HHH", 0, 1, PPQ)
    output.write_bytes(_chunk(b"MThd", header) + _chunk(b"MTrk", bytes(track)))
    return output


def write_chord_midi(
    path: str | Path,
    chords: Sequence[Sequence[int]],
    *,
    bpm: float,
    bars: int,
    seed: int,
    track_name: str = "DRUIID Chords",
    humanize_ticks: int = 5,
) -> Path:
    """Write a backwards-compatible chord clip through the strict MIDI writer."""
    if not chords:
        raise ValueError("at least one chord is required")
    if not 0 <= humanize_ticks <= 30:
        raise ValueError("humanize_ticks must be between 0 and 30")
    for chord in chords:
        if not chord or any(note < 0 or note > 127 for note in chord):
            raise ValueError("every chord must contain MIDI notes from 0 to 127")
    if isinstance(bars, bool) or not isinstance(bars, int) or bars <= 0:
        raise ValueError("bars must be a positive integer")

    rng = seeded_rng(
        seed,
        "chord-midi",
        {"bars": bars, "bpm": bpm, "chords": chords, "humanize_ticks": humanize_ticks},
    )
    total_ticks = bars * BEATS_PER_BAR * PPQ
    chord_ticks = total_ticks // len(chords)
    notes: list[MidiNote] = []
    for index, chord in enumerate(chords):
        base_tick = index * chord_ticks
        for voice, pitch in enumerate(chord):
            offset = rng.randint(0, humanize_ticks) if humanize_ticks else 0
            release_trim = min(rng.randint(8, 24), max(0, chord_ticks - offset - 1))
            end = min(total_ticks, base_tick + chord_ticks - release_trim)
            velocity = max(1, min(127, 74 + rng.randint(-8, 8) - voice * 2))
            notes.append(MidiNote(base_tick + offset, end - base_tick - offset, pitch, velocity))
    return write_midi_clip(path, notes, bpm=bpm, bars=bars, track_name=track_name)


def _read_vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise ValueError("truncated MIDI variable-length quantity")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset
    raise ValueError("invalid MIDI variable-length quantity")


def validate_midi(
    path: str | Path,
    *,
    expected_bars: int | None = None,
    expected_bpm: int | float | None = None,
    note_range: tuple[int, int] | None = None,
    drum_mapping: Mapping[str, int] | None = None,
    expected_channel: int | None = None,
) -> dict[str, int | float]:
    """Strictly validate Abletools' supported Standard MIDI subset."""
    require_capability("standard_midi")
    data = Path(path).read_bytes()
    if len(data) < 22 or data[:4] != b"MThd":
        raise ValueError("missing MIDI header")
    header_length = struct.unpack(">I", data[4:8])[0]
    if header_length != 6:
        raise ValueError("unsupported MIDI header length")
    midi_format, track_count, division = struct.unpack(">HHH", data[8:14])
    if midi_format not in (0, 1) or track_count < 1:
        raise ValueError("invalid MIDI header values")
    if midi_format == 0 and track_count != 1:
        raise ValueError("MIDI format 0 must contain exactly one track")
    if division == 0 or division & 0x8000:
        raise ValueError("MIDI must use a positive PPQ time division")

    if note_range is not None:
        if len(note_range) != 2 or not 0 <= note_range[0] <= note_range[1] <= 127:
            raise ValueError("invalid declared MIDI note range")
    declared_drum_notes: set[int] | None = None
    if drum_mapping is not None:
        if not drum_mapping or any(
            not isinstance(role, str)
            or not role
            or isinstance(note, bool)
            or not isinstance(note, int)
            or not 0 <= note <= 127
            for role, note in drum_mapping.items()
        ):
            raise ValueError("invalid declared drum mapping")
        if len(set(drum_mapping.values())) != len(drum_mapping):
            raise ValueError("declared drum mapping must use unique notes")
        declared_drum_notes = set(drum_mapping.values())

    offset = 14
    note_ons = 0
    note_offs = 0
    parsed_tracks = 0
    tempo_values: list[int] = []
    time_signatures: list[tuple[int, int]] = []
    end_ticks: list[int] = []
    used_notes: set[int] = set()
    used_channels: set[int] = set()
    for _ in range(track_count):
        if offset + 8 > len(data) or data[offset : offset + 4] != b"MTrk":
            raise ValueError("missing MIDI track chunk")
        length = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
        track = data[offset + 8 : offset + 8 + length]
        if len(track) != length:
            raise ValueError("truncated MIDI track")
        cursor = 0
        absolute_tick = 0
        running_status: int | None = None
        ended = False
        active: dict[tuple[int, int], int] = {}
        while cursor < len(track):
            delta, cursor = _read_vlq(track, cursor)
            absolute_tick += delta
            if cursor >= len(track):
                raise ValueError("truncated MIDI event")
            status = track[cursor]
            if status < 0x80:
                if running_status is None:
                    raise ValueError("invalid running status")
                status = running_status
            else:
                cursor += 1
                if status < 0xF0:
                    running_status = status
            if status == 0xFF:
                if cursor >= len(track):
                    raise ValueError("truncated MIDI meta event")
                meta_type = track[cursor]
                cursor += 1
                meta_length, cursor = _read_vlq(track, cursor)
                payload = track[cursor : cursor + meta_length]
                cursor += meta_length
                if len(payload) != meta_length:
                    raise ValueError("truncated MIDI meta payload")
                if meta_type == 0x51:
                    if meta_length != 3:
                        raise ValueError("invalid MIDI tempo event")
                    tempo_values.append(int.from_bytes(payload, "big"))
                elif meta_type == 0x58:
                    if meta_length != 4:
                        raise ValueError("invalid MIDI time-signature event")
                    time_signatures.append((payload[0], 1 << payload[1]))
                elif meta_type == 0x2F:
                    if meta_length != 0:
                        raise ValueError("invalid MIDI end-of-track event")
                    if cursor != len(track):
                        raise ValueError("unexpected data after MIDI end-of-track event")
                    ended = True
                    end_ticks.append(absolute_tick)
                    break
                continue
            if status in (0xF0, 0xF7):
                size, cursor = _read_vlq(track, cursor)
                cursor += size
                if cursor > len(track):
                    raise ValueError("truncated MIDI system-exclusive event")
                running_status = None
                continue
            if status >= 0xF0:
                raise ValueError("unsupported MIDI system event")
            event_type = status & 0xF0
            channel = status & 0x0F
            width = 1 if event_type in (0xC0, 0xD0) else 2
            payload = track[cursor : cursor + width]
            if len(payload) != width:
                raise ValueError("truncated MIDI channel event")
            if any(value >= 0x80 for value in payload):
                raise ValueError("invalid MIDI channel-event data byte")
            cursor += width
            if event_type == 0x90 and payload[1] > 0:
                key = (channel, payload[0])
                if key in active:
                    raise ValueError("overlapping note-on events for the same note")
                active[key] = absolute_tick
                used_notes.add(payload[0])
                used_channels.add(channel)
                note_ons += 1
            elif event_type == 0x80 or (event_type == 0x90 and payload[1] == 0):
                key = (channel, payload[0])
                if key not in active:
                    raise ValueError("note-off without matching note-on")
                start_tick = active.pop(key)
                if absolute_tick <= start_tick:
                    raise ValueError("MIDI contains a zero-length or reversed note")
                note_offs += 1
        if not ended:
            raise ValueError("MIDI track lacks end-of-track event")
        if active:
            raise ValueError("MIDI contains stuck notes")
        parsed_tracks += 1
        offset += 8 + length

    if note_ons == 0 or note_ons != note_offs:
        raise ValueError("MIDI note counts are invalid")
    if offset != len(data):
        raise ValueError("unexpected data after MIDI tracks")
    if not tempo_values or any(tempo <= 0 for tempo in tempo_values):
        raise ValueError("MIDI clip requires a valid tempo event")
    if not time_signatures or any(signature != (4, 4) for signature in time_signatures):
        raise ValueError("MIDI clip requires a 4/4 time-signature event")
    clip_ticks = max(end_ticks)
    ticks_per_bar = division * BEATS_PER_BAR
    if clip_ticks <= 0 or clip_ticks % ticks_per_bar:
        raise ValueError("MIDI clip length must end on a complete 4/4 bar")
    bars = clip_ticks // ticks_per_bar
    if expected_bars is not None and bars != expected_bars:
        raise ValueError(f"MIDI clip length mismatch: expected {expected_bars} bars, found {bars}")
    tempo_bpm = 60_000_000 / tempo_values[0]
    if expected_bpm is not None and abs(tempo_bpm - float(expected_bpm)) > 0.001:
        raise ValueError(f"MIDI tempo mismatch: expected {expected_bpm}, found {tempo_bpm:.6f}")
    if note_range is not None and (min(used_notes) < note_range[0] or max(used_notes) > note_range[1]):
        raise ValueError("MIDI note falls outside its declared practical range")
    if declared_drum_notes is not None and not used_notes <= declared_drum_notes:
        raise ValueError("MIDI drum note is absent from the declared drum mapping")
    if expected_channel is not None and used_channels != {expected_channel}:
        raise ValueError("MIDI events do not use the declared channel")

    return {
        "bars": bars,
        "channels": len(used_channels),
        "clip_ticks": clip_ticks,
        "format": midi_format,
        "max_note": max(used_notes),
        "min_note": min(used_notes),
        "notes": note_ons,
        "ppq": division,
        "tempo_bpm": round(tempo_bpm, 6),
        "tracks": parsed_tracks,
    }
