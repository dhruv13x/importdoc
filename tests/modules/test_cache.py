import unittest
from pathlib import Path
import tempfile
import shutil
from importdoc.modules.cache import DiagnosticCache

class TestCache(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache = DiagnosticCache(cache_dir=Path(self.test_dir))

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_cache_set_get(self):
        module_name = "test_module"
        module_path = Path(self.test_dir) / "test_module.py"
        with open(module_path, "w") as f:
            f.write("print('hello')")

        result = {"success": True, "time_ms": 10.0}
        self.cache.set(module_name, module_path, result)

        cached_result = self.cache.get(module_name, module_path)
        self.assertEqual(cached_result, result)

if __name__ == "__main__":
    unittest.main()
