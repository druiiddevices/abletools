import hashlib
import tempfile
import unittest
from pathlib import Path

from abletools.audio import validate_wav, write_kick_wav


class AudioTests(unittest.TestCase):
    def test_wav_is_24_bit_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.wav"
            second = Path(directory) / "second.wav"
            write_kick_wav(first, seed=91)
            write_kick_wav(second, seed=91)
            info = validate_wav(first)
            self.assertEqual(info["sample_rate"], 48_000)
            self.assertEqual(info["sample_width_bits"], 24)
            self.assertLessEqual(info["peak"], 1.0)
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())


if __name__ == "__main__":
    unittest.main()
