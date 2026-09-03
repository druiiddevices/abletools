import hashlib
import tempfile
import unittest
from pathlib import Path

from abletools.midi import validate_midi, write_chord_midi


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


if __name__ == "__main__":
    unittest.main()
