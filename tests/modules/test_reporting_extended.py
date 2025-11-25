# tests/modules/test_reporting_extended.py


import unittest
from unittest.mock import MagicMock, patch, ANY
import json
import os
from pathlib import Path
from importdoc.modules.reporting import DiagnosticReporter
from importdoc.modules.config import DiagnosticConfig
from importdoc.modules.autofix import AutoFix

class TestReporter(unittest.TestCase):
    def setUp(self):
        self.config = DiagnosticConfig(allow_root=True)
        self.reporter = DiagnosticReporter(self.config)
        self.reporter.logger = MagicMock()

    def test_log_emojis(self):
        self.config.use_emojis = True
        self.reporter.log("message", "INFO")
        self.reporter.logger.info.assert_called_with("ℹ️ message")

    def test_log_no_emojis(self):
        self.config.use_emojis = False
        self.reporter.log("message", "INFO")
        self.reporter.logger.info.assert_called_with("message")

    def test_print_header_package_dir(self):
        self.reporter.print_header("pkg", "/path/to/pkg")
        self.reporter.logger.info.assert_any_call("ℹ️ Package dir: /path/to/pkg")

    def test_print_summary_discovery_only(self):
        self.reporter.print_summary(set(), [], set(), {}, None, [], [], 1.0, discovery_only=True)
        self.reporter.logger.warning.assert_any_call("⚠️ Note: this was a discovery-only run (no imports performed).")

    def test_print_summary_telemetry(self):
        telemetry = {
            "total_events": 10,
            "avg_import_time_ms": 50.0,
            "slowest_imports": [{"module": "slow", "duration_ms": 100}]
        }
        # Clear mock calls to avoid noise
        self.reporter.logger.reset_mock()
        self.reporter.print_summary(set(), [], set(), {}, telemetry, [], [], 1.0)
        self.reporter.logger.info.assert_any_call("ℹ️ \n📈 Telemetry Summary:")
        self.reporter.logger.info.assert_any_call("ℹ️     - slow: 100.00ms")

    def test_print_summary_timings(self):
        self.config.verbose = True
        timings = {"mod": 1.23}
        self.reporter.logger.reset_mock()
        self.reporter.print_summary(set(), [], set(), timings, None, [], [], 1.0)
        self.reporter.logger.info.assert_any_call("ℹ️   mod: 1.23s")

    def test_print_summary_failed_modules(self):
        failed = [("mod", "err")]
        self.reporter.logger.reset_mock()
        self.reporter.print_summary(set(), failed, set(), {}, None, [], [], 1.0)
        self.reporter.logger.error.assert_any_call("❌ \n❌ FAILED MODULES:")
        self.reporter.logger.error.assert_any_call("❌   • mod: err")

    def test_print_summary_success(self):
        self.reporter.logger.reset_mock()
        self.reporter.print_summary({"mod"}, [], set(), {}, None, [], [], 1.0)
        self.reporter.logger.info.assert_any_call("ℹ️ \n🎉 ALL MODULES IMPORTED SUCCESSFULLY!")

    def test_print_json_summary(self):
        with patch("sys.stdout.write") as mock_write:
            self.reporter.print_json_summary("pkg", {"mod"}, [], {"mod"}, [], set(), {}, {"pkg": ["mod"]}, {}, [], None, 1.0)
            mock_write.assert_called()
            args = mock_write.call_args[0][0]
            data = json.loads(args)
            self.assertEqual(data["package"], "pkg")

    def test_print_json_summary_schema_fail(self):
         # Creating data that fails schema is hard if schema is permissive, but we can verify it logs warning if validate_json mock returns False
         with patch("importdoc.modules.reporting.validate_json", return_value=False):
             with patch("sys.stdout.write"):
                 self.reporter.print_json_summary("pkg", set(), [], set(), [], set(), {}, {}, {}, [], None, 1.0)
                 self.reporter.logger.warning.assert_called_with("⚠️ Summary JSON failed schema validation. Outputting anyway.")

    def test_export_fixes_success(self):
        fix = AutoFix(
            issue_type="missing_dep",
            module_name="pkg",
            confidence=1.0,
            description="desc",
            patch=None,
            manual_steps=[]
        )
        with patch("tempfile.NamedTemporaryFile") as mock_tmp:
            mock_tmp.return_value.__enter__.return_value.name = "tmp"
            with patch("os.replace") as mock_replace:
                self.reporter.export_fixes([fix])
                mock_replace.assert_called()

    def test_export_fixes_fail(self):
        fix = AutoFix(
            issue_type="missing_dep",
            module_name="pkg",
            confidence=1.0,
            description="desc",
            patch=None,
            manual_steps=[]
        )
        with patch("os.replace", side_effect=Exception("fail")):
            # We also need tempfile to work
             with patch("tempfile.NamedTemporaryFile") as mock_tmp:
                  mock_tmp.return_value.__enter__.return_value.name = "tmp"
                  self.reporter.export_fixes([fix])
                  self.reporter.logger.warning.assert_called()

    def test_export_graph_success(self):
        self.config.dot_file = "out.dot"
        edges = {("a", "b")}
        with patch("tempfile.NamedTemporaryFile") as mock_tmp:
            mock_tmp.return_value.__enter__.return_value.name = "tmp"
            with patch("os.replace") as mock_replace:
                self.reporter.export_graph(edges, set())
                mock_replace.assert_called()

    def test_diagnose_path_issue_found(self):
        mock_path = MagicMock(spec=Path)
        mock_path.stat.return_value.st_mode = 0o755
        mock_path.__str__.return_value = "/path/to/file"
        with patch("importdoc.modules.utils.find_module_file_path", return_value=mock_path):
            self.reporter.diagnose_path_issue("mod")
            self.reporter.logger.info.assert_any_call("ℹ️ Found file: /path/to/file")

    def test_diagnose_path_issue_not_found(self):
        with patch("importdoc.modules.utils.find_module_file_path", return_value=None):
            self.reporter.diagnose_path_issue("mod")
            self.reporter.logger.info.assert_any_call("ℹ️ No file found matching module.")

    def test_setup_logger_with_file(self):
        import logging
        with patch("importdoc.modules.reporting.RotatingFileHandler") as mock_handler:
             # Reset initialized flag on the REAL logger
             real_logger = logging.getLogger("import_diagnostic")
             if hasattr(real_logger, "_initialized_by_import_diag"):
                 del real_logger._initialized_by_import_diag

             logger = self.reporter._setup_logger("log.txt", 10)
             mock_handler.assert_called()
             self.assertIn(mock_handler.return_value, logger.handlers)
             logger.removeHandler(mock_handler.return_value) # cleanup

if __name__ == "__main__":
    unittest.main()
