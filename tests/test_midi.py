import hashlib
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
