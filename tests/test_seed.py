import unittest

from abletools.seed import derive_seed


class SeedTests(unittest.TestCase):
    def test_seed_is_stable_and_namespaced(self) -> None:
        first = derive_seed(1842, "midi", {"key": "A minor"})
        self.assertEqual(first, derive_seed(1842, "midi", {"key": "A minor"}))
        self.assertNotEqual(first, derive_seed(1842, "wav", {"key": "A minor"}))

    def test_bool_is_not_a_seed(self) -> None:
        with self.assertRaises(TypeError):
            derive_seed(True, "midi")


if __name__ == "__main__":
    unittest.main()
