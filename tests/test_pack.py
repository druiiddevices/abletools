import tempfile
import unittest
from pathlib import Path

from abletools.pack import build_demo_pack, validate_pack


class PackTests(unittest.TestCase):
    def test_demo_pack_builds_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "demo"
            build_demo_pack(root, 1842)
            results = validate_pack(root)
            self.assertEqual(len(results), 2)
            self.assertTrue(root.with_suffix(".zip").is_file())


if __name__ == "__main__":
    unittest.main()
