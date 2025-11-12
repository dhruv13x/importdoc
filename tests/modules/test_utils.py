import unittest
from pathlib import Path
import tempfile
import shutil
from src.importdoc.modules.utils import (
    safe_read_text,
    analyze_ast_symbols,
    find_module_file_path,
    suggest_pip_names,
    is_standard_lib,
    detect_env,
)

class TestUtils(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_safe_read_text(self):
        test_file = Path(self.test_dir) / "test.txt"
        with open(test_file, "w") as f:
            f.write("hello")
        self.assertEqual(safe_read_text(test_file), "hello")

    def test_analyze_ast_symbols(self):
        test_file = Path(self.test_dir) / "test.py"
        with open(test_file, "w") as f:
            f.write("def my_func(): pass\nclass MyClass: pass")
        symbols = analyze_ast_symbols(test_file)
        self.assertIn("my_func", symbols["functions"])
        self.assertIn("MyClass", symbols["classes"])

    def test_is_standard_lib(self):
        self.assertTrue(is_standard_lib("os"))
        self.assertFalse(is_standard_lib("non_existent_module"))

    def test_detect_env(self):
        env = detect_env()
        self.assertIn("virtualenv", env)
        self.assertIn("editable", env)

if __name__ == "__main__":
    unittest.main()
