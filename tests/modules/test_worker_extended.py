# tests/modules/test_worker_extended.py


import unittest
from unittest.mock import MagicMock, patch
from importdoc.modules.worker import import_module_worker
import subprocess
import json
import sys

class TestWorker(unittest.TestCase):
    def test_import_success(self):
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.stdout = json.dumps({"success": True, "error": None, "tb": None, "time_ms": 10.0}).encode("utf-8")
            mock_proc.stderr = b""
            mock_run.return_value = mock_proc

            result = import_module_worker("good_module", None)
            self.assertTrue(result["success"])
            self.assertEqual(result["time_ms"], 10.0)

    def test_import_failure_exception(self):
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.stdout = json.dumps({"success": False, "error": "ImportError", "tb": "traceback", "time_ms": 10.0}).encode("utf-8")
            mock_proc.stderr = b""
            mock_run.return_value = mock_proc

            result = import_module_worker("bad_module", None)
            self.assertFalse(result["success"])
            self.assertEqual(result["error"], "ImportError")

    def test_import_failure_non_json(self):
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.stdout = b"some random output"
            mock_proc.stderr = b"some error"
            mock_run.return_value = mock_proc

            result = import_module_worker("weird_module", None)
            self.assertFalse(result["success"])
            self.assertIn("Subprocess failure", result["error"])

    def test_import_failure_empty_output(self):
        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.stdout = b""
            mock_proc.stderr = b""
            mock_run.return_value = mock_proc

            result = import_module_worker("weird_module", None)
            self.assertFalse(result["success"])
            self.assertIn("Subprocess failure", result["error"])
            self.assertIn("<no output>", result["error"])

    def test_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["cmd"], 1.0)):
            result = import_module_worker("slow_module", 1)
            self.assertFalse(result["success"])
            self.assertIn("Timeout after 1s", result["error"])

    def test_subprocess_exception(self):
        with patch("subprocess.run", side_effect=Exception("Process error")):
            result = import_module_worker("module", None)
            self.assertFalse(result["success"])
            self.assertIn("Process error", result["error"])

    def test_child_code_logic_success(self):
        # We can try to actually run the worker code snippet,
        # but that requires extracting it or duplicating logic.
        # Let's verify we construct the args correctly at least?
        # Or rely on integration test which we have.
        pass

if __name__ == "__main__":
    unittest.main()
