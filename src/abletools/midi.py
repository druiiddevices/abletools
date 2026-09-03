"""Minimal dependency-free Standard MIDI generation and validation."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable, Sequence

from .seed import seeded_rng

PPQ = 480


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
    """Write a type-0 chord clip whose timing and velocities are seed-stable."""
    if not chords:
        raise ValueError("at least one chord is required")
    if bpm <= 0 or bars <= 0:
        raise ValueError("bpm and bars must be positive")
    if not 0 <= humanize_ticks <= 30:
        raise ValueError("humanize_ticks must be between 0 and 30")
    for chord in chords:
        if not chord or any(note < 0 or note > 127 for note in chord):
            raise ValueError("every chord must contain MIDI notes from 0 to 127")

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    rng = seeded_rng(seed, "chord-midi", {"bpm": bpm, "bars": bars, "chords": chords})
    total_ticks = bars * 4 * PPQ
    chord_ticks = total_ticks // len(chords)
    timed_events: list[tuple[int, int, bytes]] = []

    for index, chord in enumerate(chords):
        base_tick = index * chord_ticks
        for voice, note in enumerate(chord):
            offset = rng.randint(0, humanize_ticks) if humanize_ticks else 0
            start = base_tick + offset
            release_trim = rng.randint(8, 24)
            end = min(total_ticks, base_tick + chord_ticks - release_trim)
            velocity = max(1, min(127, 74 + rng.randint(-8, 8) - voice * 2))
            timed_events.append((start, 1, bytes((0x90, note, velocity))))
            timed_events.append((end, 0, bytes((0x80, note, 0))))

    timed_events.sort(key=lambda item: (item[0], item[1]))
    tempo = round(60_000_000 / bpm)
    name = track_name.encode("utf-8")[:127]
    track = bytearray()
    track += _event(0, b"\xFF\x03" + _vlq(len(name)) + name)
    track += _event(0, b"\xFF\x51\x03" + tempo.to_bytes(3, "big"))
    track += _event(0, b"\xFF\x58\x04\x04\x02\x18\x08")

    last_tick = 0
    for tick, _priority, payload in timed_events:
        track += _event(tick - last_tick, payload)
        last_tick = tick
    track += _event(max(0, total_ticks - last_tick), b"\xFF\x2F\x00")

    header = struct.pack(">HHH", 0, 1, PPQ)
    output.write_bytes(_chunk(b"MThd", header) + _chunk(b"MTrk", bytes(track)))
    return output


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


def validate_midi(path: str | Path) -> dict[str, int]:
    """Validate the subset of Standard MIDI required by Abletools outputs."""
    data = Path(path).read_bytes()
    if len(data) < 22 or data[:4] != b"MThd":
        raise ValueError("missing MIDI header")
    header_length = struct.unpack(">I", data[4:8])[0]
    if header_length != 6:
        raise ValueError("unsupported MIDI header length")
    midi_format, track_count, division = struct.unpack(">HHH", data[8:14])
    if midi_format not in (0, 1) or track_count < 1 or division == 0:
        raise ValueError("invalid MIDI header values")

    offset = 14
    note_ons = 0
    note_offs = 0
    parsed_tracks = 0
    for _ in range(track_count):
        if data[offset : offset + 4] != b"MTrk":
            raise ValueError("missing MIDI track chunk")
        length = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
        track = data[offset + 8 : offset + 8 + length]
        if len(track) != length:
            raise ValueError("truncated MIDI track")
        cursor = 0
        running_status: int | None = None
        ended = False
        active: dict[tuple[int, int], int] = {}
        while cursor < len(track):
            _delta, cursor = _read_vlq(track, cursor)
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
                cursor += meta_length
                if cursor > len(track):
                    raise ValueError("truncated MIDI meta payload")
                if meta_type == 0x2F:
                    ended = True
                    break
                continue
            if status in (0xF0, 0xF7):
                size, cursor = _read_vlq(track, cursor)
                cursor += size
                continue
            event_type = status & 0xF0
            channel = status & 0x0F
            width = 1 if event_type in (0xC0, 0xD0) else 2
            payload = track[cursor : cursor + width]
            if len(payload) != width:
                raise ValueError("truncated MIDI channel event")
            cursor += width
            if event_type == 0x90 and payload[1] > 0:
                key = (channel, payload[0])
                active[key] = active.get(key, 0) + 1
                note_ons += 1
            elif event_type == 0x80 or (event_type == 0x90 and payload[1] == 0):
                key = (channel, payload[0])
                if active.get(key, 0) <= 0:
                    raise ValueError("note-off without matching note-on")
                active[key] -= 1
                note_offs += 1
        if not ended:
            raise ValueError("MIDI track lacks end-of-track event")
        if any(active.values()):
            raise ValueError("MIDI contains stuck notes")
        parsed_tracks += 1
        offset += 8 + length

    if note_ons == 0 or note_ons != note_offs:
        raise ValueError("MIDI note counts are invalid")
    if offset != len(data):
        raise ValueError("unexpected data after MIDI tracks")
    return {"format": midi_format, "tracks": parsed_tracks, "ppq": division, "notes": note_ons}
