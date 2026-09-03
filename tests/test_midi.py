import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from abletools.midi import MidiNote, validate_midi, write_chord_midi, write_midi_clip


class MidiTests(unittest.TestCase):
    def test_midi_is_valid_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.mid"
            second = Path(directory) / "second.mid"
            kwargs = {"chords": [[60, 64, 67], [57, 60, 64]], "bpm": 120, "bars": 4, "seed": 77}
            write_chord_midi(first, **kwargs)
            write_chord_midi(second, **kwargs)
            info = validate_midi(first)
            self.assertEqual(info["notes"], 6)
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())

    def test_invalid_note_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                write_chord_midi(Path(directory) / "bad.mid", [[128]], bpm=120, bars=1, seed=1)

    def test_strict_clip_contract_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mid"
            write_midi_clip(path, [MidiNote(0, 240, 60, 90)], bpm=100, bars=2, track_name="test")
            info = validate_midi(path, expected_bars=2, expected_bpm=100, note_range=(48, 72))
            self.assertEqual(info["bars"], 2)
            self.assertEqual(info["clip_ticks"], 2 * 4 * 480)

    def test_declared_midi_format_and_ppq_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mid"
            write_midi_clip(path, [MidiNote(0, 240, 60, 90)], bpm=120, bars=1, track_name="test")
            with self.assertRaisesRegex(ValueError, "MIDI format mismatch"):
                validate_midi(path, expected_midi_format=1)
            with self.assertRaisesRegex(ValueError, "MIDI PPQ mismatch"):
                validate_midi(path, expected_ppq=960)

    def test_extra_conflicting_tempo_event_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "extra-tempo.mid"
            write_midi_clip(path, [MidiNote(0, 240, 60, 90)], bpm=120, bars=1, track_name="test")
            data = bytearray(path.read_bytes())
            extra_tempo = b"\x00\xff\x51\x03\x09\x27\xc0"
            track_length = struct.unpack(">I", data[18:22])[0]
            data[18:22] = struct.pack(">I", track_length + len(extra_tempo))
            data[22:22] = extra_tempo
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "exactly one tempo event"):
                validate_midi(path)

    def test_tempo_event_not_at_tick_zero_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "late-tempo.mid"
            write_midi_clip(path, [MidiNote(0, 240, 60, 90)], bpm=120, bars=1, track_name="test")
            data = path.read_bytes()
            marker = b"\x00\xff\x51\x03"
            self.assertEqual(data.count(marker), 1)
            path.write_bytes(data.replace(marker, b"\x01\xff\x51\x03", 1))
            with self.assertRaisesRegex(ValueError, "tempo event must occur at tick 0"):
                validate_midi(path)

    def test_extra_time_signature_event_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "extra-meter.mid"
            write_midi_clip(path, [MidiNote(0, 240, 60, 90)], bpm=120, bars=1, track_name="test")
            data = bytearray(path.read_bytes())
            extra_meter = b"\x00\xff\x58\x04\x04\x02\x18\x08"
            track_length = struct.unpack(">I", data[18:22])[0]
            data[18:22] = struct.pack(">I", track_length + len(extra_meter))
            data[22:22] = extra_meter
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "exactly one time-signature event"):
                validate_midi(path)

    def test_time_signature_event_not_at_tick_zero_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "late-meter.mid"
            write_midi_clip(path, [MidiNote(0, 240, 60, 90)], bpm=120, bars=1, track_name="test")
            data = path.read_bytes()
            marker = b"\x00\xff\x58\x04"
            self.assertEqual(data.count(marker), 1)
            path.write_bytes(data.replace(marker, b"\x01\xff\x58\x04", 1))
            with self.assertRaisesRegex(ValueError, "time-signature event must occur at tick 0"):
                validate_midi(path)

    def test_zero_length_and_overlapping_notes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.mid"
            with self.assertRaisesRegex(ValueError, "positive integer durations"):
                write_midi_clip(path, [MidiNote(0, 0, 60, 90)], bpm=120, bars=1, track_name="bad")
            with self.assertRaisesRegex(ValueError, "overlapping events"):
                write_midi_clip(
                    path,
                    [MidiNote(0, 240, 60, 90), MidiNote(120, 240, 60, 90)],
                    bpm=120,
                    bars=1,
                    track_name="bad",
                )

    def test_corrupt_zero_length_note_is_rejected_by_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.mid"
            write_midi_clip(path, [MidiNote(0, 120, 60, 90)], bpm=120, bars=1, track_name="test")
            data = path.read_bytes()
            original = b"\x78\x80\x3c\x00"
            self.assertIn(original, data)
            path.write_bytes(data.replace(original, b"\x00\x80\x3c\x00", 1))
            with self.assertRaisesRegex(ValueError, "zero-length"):
                validate_midi(path)

    def test_clip_length_range_mapping_and_trailing_data_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mid"
            write_midi_clip(path, [MidiNote(0, 120, 36, 90, channel=9)], bpm=120, bars=1, track_name="test")
            with self.assertRaisesRegex(ValueError, "length mismatch"):
                validate_midi(path, expected_bars=2)
            with self.assertRaisesRegex(ValueError, "practical range"):
                validate_midi(path, note_range=(40, 60))
            with self.assertRaisesRegex(ValueError, "drum note"):
                validate_midi(path, drum_mapping={"snare": 38}, expected_channel=9)
            path.write_bytes(path.read_bytes() + b"junk")
            with self.assertRaisesRegex(ValueError, "after MIDI tracks"):
                validate_midi(path)


if __name__ == "__main__":
    unittest.main()
