import unittest
from importdoc.modules.worker import import_module_worker

class TestWorker(unittest.TestCase):
    def test_import_module_worker_success(self):
        result = import_module_worker("os", timeout=5)
        self.assertTrue(result["success"])
        self.assertIsNone(result["error"])

    def test_import_module_worker_failure(self):
        result = import_module_worker("non_existent_module", timeout=5)
        self.assertFalse(result["success"])
        self.assertIsNotNone(result["error"])
        self.assertIn("No module named", result["error"])

if __name__ == "__main__":
    unittest.main()
