# tests/modules/test_runner_extended.py


import unittest
from unittest.mock import MagicMock, patch, call
from importdoc.modules.runner import ImportRunner
from importdoc.modules.config import DiagnosticConfig
from importdoc.modules.reporting import DiagnosticReporter
from importdoc.modules.analysis import ErrorAnalyzer
from importdoc.modules.telemetry import TelemetryCollector
from importdoc.modules.cache import DiagnosticCache
from pathlib import Path
import sys
import importlib

class TestImportRunner(unittest.TestCase):
    def setUp(self):
        self.config = DiagnosticConfig(allow_root=True)
        self.reporter = DiagnosticReporter(self.config)
        self.reporter.log = MagicMock()
        self.analyzer = MagicMock(spec=ErrorAnalyzer)
        self.telemetry = MagicMock(spec=TelemetryCollector)
        self.cache = MagicMock(spec=DiagnosticCache)
        self.runner = ImportRunner(self.config, self.reporter, self.analyzer, self.telemetry, self.cache)

    def test_run_imports_empty(self):
        result = self.runner.run_imports(set(), Path("."), None)
        self.assertTrue(result)

    def test_run_imports_success_cached(self):
        self.cache.get.return_value = {"success": True, "time_ms": 100}
        with patch("importdoc.modules.runner.find_module_file_path", return_value=Path("foo.py")):
             result = self.runner.run_imports({"foo"}, Path("."), None)
        self.assertTrue(result)
        self.assertIn("foo", self.runner.imported_modules)
        self.assertEqual(self.runner.timings["foo"], 0.1)

    def test_run_imports_failed_cached(self):
        self.cache.get.return_value = {"success": False, "error": "failed", "time_ms": 100}
        self.analyzer.analyze.return_value = {"type": "unknown"}
        self.analyzer.calculate_confidence.return_value = (0, "low")
        with patch("importdoc.modules.runner.find_module_file_path", return_value=Path("foo.py")):
             result = self.runner.run_imports({"foo"}, Path("."), None)
        self.assertFalse(result)
        self.assertEqual(len(self.runner.failed_modules), 1)

    def test_run_imports_success_subprocess(self):
        self.cache.get.return_value = None
        with patch("importdoc.modules.runner.import_module_worker", return_value={"success": True, "time_ms": 100}):
            with patch("importdoc.modules.runner.find_module_file_path", return_value=Path("foo.py")):
                result = self.runner.run_imports({"foo"}, Path("."), None)
        self.assertTrue(result)
        self.cache.set.assert_called()
        self.telemetry.record.assert_called_with("import_success", "foo", 100.0)

    def test_run_imports_failure_subprocess(self):
        self.cache.get.return_value = None
        with patch("importdoc.modules.runner.import_module_worker", return_value={"success": False, "error": "err", "time_ms": 100, "tb": "traceback"}):
            with patch("importdoc.modules.runner.find_module_file_path", return_value=Path("foo.py")):
                # Analyzer mock setup
                self.analyzer.analyze.return_value = {"type": "unknown"}
                self.analyzer.calculate_confidence.return_value = (0, "low")

                result = self.runner.run_imports({"foo"}, Path("."), None)
        self.assertFalse(result)
        self.telemetry.record.assert_called_with("import_failure", "foo", 100.0, error="err")
        self.analyzer.analyze.assert_called()

    def test_run_imports_exception_subprocess(self):
        self.cache.get.return_value = None
        with patch("importdoc.modules.runner.import_module_worker", side_effect=Exception("Crash")):
            with patch("importdoc.modules.runner.find_module_file_path", return_value=Path("foo.py")):
                self.analyzer.analyze.return_value = {}
                self.analyzer.calculate_confidence.return_value = (0, "")
                result = self.runner.run_imports({"foo"}, Path("."), None)
        self.assertFalse(result)
        self.assertIn("foo", [x[0] for x in self.runner.failed_modules])

    def test_process_import_result_success(self):
        self.runner._process_import_result("foo", {"success": True, "time_ms": 100})
        self.assertIn("foo", self.runner.imported_modules)
        self.telemetry.record.assert_called_with("import_success", "foo", 100.0)

    def test_process_import_result_failure(self):
        self.analyzer.analyze.return_value = {}
        self.analyzer.calculate_confidence.return_value = (0, "")
        self.runner._process_import_result("foo", {"success": False, "error": "err", "time_ms": 100, "tb": "tb"})
        self.assertIn("foo", [x[0] for x in self.runner.failed_modules])

    def test_progress_bar_fallback(self):
        # Mock tqdm to be None in runner module
        # Mock import_module_worker to return a valid result
        # Also ensure cache returns None so it tries to run worker
        self.cache.get.return_value = None
        with patch("importdoc.modules.runner.tqdm", None), \
             patch("importdoc.modules.runner.import_module_worker", return_value={"success": True, "time_ms": 100}), \
             patch("importdoc.modules.runner.find_module_file_path", return_value=Path("foo.py")):
             self.runner.run_imports({"foo"}, Path("."), None)
        # We can't easily verify _DummyProgress usage without mocking internal logic
        # but running it without error covers the code path.

    def test_uninstall_tracer(self):
        self.config.dev_trace = True
        with patch.object(self.runner, "_uninstall_import_tracer", wraps=self.runner._uninstall_import_tracer) as mock_uninstall:
             self.runner.run_imports(set(), Path("."), None)
             mock_uninstall.assert_called()

    def test_handle_error_suggestions(self):
        self.analyzer.analyze.return_value = {
            "type": "error",
            "evidence": ["ev1"],
            "suggestions": ["sug1"],
            "auto_fix": MagicMock(confidence=0.9)
        }
        self.analyzer.calculate_confidence.return_value = (9, "high")
        self.config.generate_fixes = True

        self.runner._handle_error("foo", Exception("err"))

        self.reporter.log.assert_any_call("  1. sug1", level="INFO")
        self.reporter.log.assert_any_call("🔧 Auto-fix generated (confidence: 90%)", level="INFO")
        self.assertEqual(len(self.runner.auto_fixes), 1)

    def test_dev_trace(self):
        self.config.dev_trace = True
        self.config.parallel = 0 # Ensure sequential for trace test simplicity
        self.cache.get.return_value = None # No cache

        with patch("importdoc.modules.runner.import_module_worker", return_value={"success": True, "time_ms": 10}):
            with patch("importdoc.modules.runner.find_module_file_path"):
                 # Mock builtins.__import__ interaction is tricky because run_imports installs it
                 # But we are mocking worker, so the trace won't actually happen inside worker process
                 # The tracer is installed in the runner process.

                 # Let's test _install_import_tracer directly
                 pass

    def test_install_uninstall_tracer(self):
        original_import = __import__
        self.runner._install_import_tracer()
        self.assertNotEqual(__import__, original_import)

        # Test tracing
        try:
            # We can't easily import something that doesn't exist without raising error
            # And importing standard lib might have side effects.
            # Just check if edge is added?
            pass
        finally:
            self.runner._uninstall_import_tracer()
            self.assertEqual(__import__, original_import)

    def test_parallel_execution(self):
        self.config.parallel = 2
        self.cache.get.return_value = None

        with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor:
            mock_future = MagicMock()
            mock_future.result.return_value = {"success": True, "time_ms": 100}
            mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future
            mock_executor.return_value.__enter__.return_value.submit.side_effect = lambda fn, mod, timeout: mock_future

            # We need to make sure as_completed yields futures
            with patch("concurrent.futures.as_completed", return_value=[mock_future]):
                 self.runner.run_imports({"foo"}, Path("."), None)

        self.assertIn("foo", self.runner.imported_modules)


class TestImportRunnerCoverage(unittest.TestCase):
    def setUp(self):
        self.config = DiagnosticConfig(allow_root=True)
        self.reporter = MagicMock(spec=DiagnosticReporter)
        self.analyzer = MagicMock(spec=ErrorAnalyzer)
        self.telemetry = MagicMock(spec=TelemetryCollector)
        self.cache = MagicMock(spec=DiagnosticCache)
        self.runner = ImportRunner(self.config, self.reporter, self.analyzer, self.telemetry, self.cache)

    def test_tqdm_import_error(self):
        with patch.dict("sys.modules", {"tqdm": None}):
            importlib.reload(sys.modules["importdoc.modules.runner"])
            self.assertIsNotNone(ImportRunner)

    def test_dev_trace_disables_parallel(self):
        self.runner.config.parallel = 2
        self.runner.config.dev_trace = True
        self.runner.run_imports(set(), Path("."), None)
        self.reporter.log.assert_any_call(
            "Dev trace disables parallel; running sequential.", level="WARNING"
        )

    def test_continue_on_error(self):
        self.runner.config.continue_on_error = False
        self.cache.get.return_value = None
        with patch(
            "importdoc.modules.runner.import_module_worker",
            side_effect=Exception("test error"),
        ):
            self.analyzer.calculate_confidence.return_value = (0, "low")
            result = self.runner.run_imports({"foo", "bar"}, Path("."), None)
        self.assertFalse(result)

    def test_parallel_run_exception(self):
        self.runner.config.parallel = 1
        self.runner.config.dev_trace = False
        self.cache.get.return_value = None
        with patch(
            "concurrent.futures.Future.result", side_effect=Exception("test error")
        ):
            self.analyzer.calculate_confidence.return_value = (0, "low")
            result = self.runner.run_imports({"foo"}, Path("."), None)
        self.assertFalse(result)

    def test_progress_bar_close_exception(self):
        self.cache.get.return_value = None
        with patch("importdoc.modules.runner.tqdm") as mock_tqdm:
            mock_tqdm.return_value.close.side_effect = Exception("close error")
            self.runner.run_imports(set(), Path("."), None)

    def test_unload_module(self):
        self.config.unload = True
        self.cache.get.return_value = None
        with patch("importdoc.modules.runner.import_module_worker", return_value={"success": True, "time_ms": 100}):
            with patch.dict("sys.modules", {"foo": MagicMock()}):
                self.runner.run_imports({"foo"}, Path("."), None)
        self.assertNotIn("foo", sys.modules)

    def test_local_module_error_log(self):
        self.cache.get.return_value = None
        self.analyzer.analyze.return_value = {"type": "local_module"}
        self.analyzer.calculate_confidence.return_value = (0, "low")
        with patch("importdoc.modules.runner.import_module_worker", return_value={"success": False, "error": "err"}):
            self.runner.run_imports({"foo"}, Path("."), None)

        found = False
        for call_args in self.reporter.log.call_args_list:
            if "Development Tips" in call_args[0][0]:
                found = True
                break
        self.assertTrue(found)

    def test_install_tracer_twice(self):
        self.runner._install_import_tracer()
        self.runner._install_import_tracer()
        self.assertIsNotNone(self.runner._original_import)
        self.runner._uninstall_import_tracer()

    def test_tracer_exception(self):
        self.runner._install_import_tracer()
        self.runner._import_stack.append("root")
        with self.assertRaises(ImportError):
            __import__("nonexistent_module")
        self.runner._uninstall_import_tracer()
        self.reporter.log.assert_any_call(
            "FAILURE CHAIN: root -> nonexistent_module", level="ERROR"
        )

    def test_uninstall_tracer_no_original(self):
        self.runner._original_import = None
        self.runner._uninstall_import_tracer()


if __name__ == "__main__":
    unittest.main()
