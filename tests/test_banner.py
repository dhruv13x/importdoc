import unittest
from unittest.mock import patch
from importdoc import banner
import os

class TestBanner(unittest.TestCase):
    def test_lerp(self):
        self.assertEqual(banner.lerp(0, 10, 0.5), 5)

    def test_blend(self):
        c1 = (0, 0, 0)
        c2 = (255, 255, 255)
        self.assertIsNotNone(banner.blend(c1, c2, 0.5))

    @patch.dict(os.environ, {"CREATE_DUMP_PALETTE": "0"})
    def test_print_logo_with_env_var(self):
        banner.print_logo()

    @patch.dict(os.environ, {"CREATE_DUMP_PALETTE": "invalid"})
    def test_print_logo_with_invalid_env_var(self):
        banner.print_logo()

    def test_print_logo_without_env_var(self):
        if "CREATE_DUMP_PALETTE" in os.environ:
            del os.environ["CREATE_DUMP_PALETTE"]
        banner.print_logo()

if __name__ == "__main__":
    unittest.main()
