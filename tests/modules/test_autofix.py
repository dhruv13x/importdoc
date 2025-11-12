import unittest
from src.importdoc.modules.autofix import FixGenerator

class TestAutofix(unittest.TestCase):
    def test_generate_missing_import_fix(self):
        fix = FixGenerator.generate_missing_import_fix("old_module", "my_symbol", "new_module")
        self.assertEqual(fix.issue_type, "missing_import")
        self.assertIn("old_module", fix.description)
        self.assertIn("new_module", fix.description)
        self.assertIsNotNone(fix.patch)

    def test_generate_circular_import_fix(self):
        fix = FixGenerator.generate_circular_import_fix(["mod1", "mod2", "mod1"])
        self.assertEqual(fix.issue_type, "circular_import")
        self.assertIn("mod1 -> mod2 -> mod1", fix.description)
        self.assertIsNone(fix.patch)

    def test_generate_missing_dependency_fix(self):
        fix = FixGenerator.generate_missing_dependency_fix("my_package", "my-package")
        self.assertEqual(fix.issue_type, "missing_dependency")
        self.assertIn("my_package", fix.description)
        self.assertIn("Install package: pip install my-package", fix.manual_steps)
        self.assertIsNone(fix.patch)

if __name__ == "__main__":
    unittest.main()
