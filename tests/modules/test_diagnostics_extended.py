# tests/modules/test_diagnostics_extended.py


import unittest
from unittest.mock import MagicMock, patch
from importdoc.modules.diagnostics import ImportDiagnostic
import sys
from pathlib import Path

class TestImportDiagnostic(unittest.TestCase):
    def setUp(self):
        self.diagnostic = ImportDiagnostic(allow_root=True)
        self.diagnostic.reporter = MagicMock()
        self.diagnostic.discoverer = MagicMock()
        self.diagnostic.runner = MagicMock()

    def test_run_diagnostic_success(self):
        # We need to ensure _skip_imports_enforced_by_safe_mode is False.
        # It is set in __init__, so we can manually override it on the instance.
        self.diagnostic._skip_imports_enforced_by_safe_mode = False

        self.diagnostic.discoverer.validate_package.return_value = True
        discovery_result = MagicMock()
        discovery_result.discovered_modules = {"foo"}
        discovery_result.discovery_errors = []
        discovery_result.skipped_modules = set()
        discovery_result.package_tree = {}
        self.diagnostic.discoverer.discover.return_value = discovery_result

        self.diagnostic.runner.run_imports.return_value = True
        self.diagnostic.runner.failed_modules = []
        self.diagnostic.runner.auto_fixes = []
        self.diagnostic.runner.edges = set()

        result = self.diagnostic.run_diagnostic("foo")
        self.assertTrue(result)
        self.diagnostic.runner.run_imports.assert_called()

    def test_run_diagnostic_validate_fail(self):
        self.diagnostic.discoverer.validate_package.return_value = False
        result = self.diagnostic.run_diagnostic("foo")
        self.assertFalse(result)

    def test_run_diagnostic_discovery_only(self):
        self.diagnostic.config.dry_run = True
        self.diagnostic.discoverer.validate_package.return_value = True
        discovery_result = MagicMock()
        discovery_result.discovery_errors = []
        self.diagnostic.discoverer.discover.return_value = discovery_result

        result = self.diagnostic.run_diagnostic("foo")
        self.assertTrue(result)
        self.diagnostic.runner.run_imports.assert_not_called()

    def test_run_diagnostic_safe_mode_skip(self):
        # safe mode is true by default
        self.diagnostic.env_info["virtualenv"] = False
        self.diagnostic._check_environment()
        self.assertTrue(self.diagnostic._skip_imports_enforced_by_safe_mode)

        self.diagnostic.discoverer.validate_package.return_value = True
        discovery_result = MagicMock()
        discovery_result.discovery_errors = []
        self.diagnostic.discoverer.discover.return_value = discovery_result

        result = self.diagnostic.run_diagnostic("foo")
        self.assertTrue(result)
        self.diagnostic.runner.run_imports.assert_not_called()

    def test_run_diagnostic_with_package_dir(self):
        self.diagnostic.discoverer.validate_package.return_value = True
        discovery_result = MagicMock()
        discovery_result.discovery_errors = []
        self.diagnostic.discoverer.discover.return_value = discovery_result
        self.diagnostic.runner.failed_modules = []
        self.diagnostic.runner.auto_fixes = []
        self.diagnostic.runner.edges = set()

        with patch("sys.path", []) as mock_sys_path:
             with patch("pathlib.Path.resolve", return_value=Path("/tmp/pkg")):
                 result = self.diagnostic.run_diagnostic("pkg", "/tmp/pkg")
                 self.assertIn(str(Path("/tmp")), mock_sys_path)

    def test_run_diagnostic_generate_fixes(self):
        self.diagnostic.config.generate_fixes = True
        self.diagnostic.discoverer.validate_package.return_value = True
        discovery_result = MagicMock()
        discovery_result.discovery_errors = []
        self.diagnostic.discoverer.discover.return_value = discovery_result
        self.diagnostic.runner.failed_modules = []
        self.diagnostic.runner.auto_fixes = ["fix"]
        self.diagnostic.runner.edges = set()

        self.diagnostic.run_diagnostic("foo")
        self.diagnostic.reporter.export_fixes.assert_called_with(["fix"])

    def test_run_diagnostic_json_output(self):
        self.diagnostic.config.json_output = True
        self.diagnostic.discoverer.validate_package.return_value = True
        discovery_result = MagicMock()
        discovery_result.discovery_errors = []
        self.diagnostic.discoverer.discover.return_value = discovery_result
        self.diagnostic.runner.failed_modules = []
        self.diagnostic.runner.auto_fixes = []
        self.diagnostic.runner.edges = set()

        self.diagnostic.run_diagnostic("foo")
        self.diagnostic.reporter.print_json_summary.assert_called()

    def test_run_diagnostic_failure(self):
        self.diagnostic.discoverer.validate_package.return_value = True
        discovery_result = MagicMock()
        discovery_result.discovery_errors = []
        self.diagnostic.discoverer.discover.return_value = discovery_result
        self.diagnostic.runner.failed_modules = [("foo", "err")]
        self.diagnostic.runner.auto_fixes = []
        self.diagnostic.runner.edges = set()

        result = self.diagnostic.run_diagnostic("foo")
        self.assertFalse(result)

    def test_run_diagnostic_discovery_error(self):
        self.diagnostic.discoverer.validate_package.return_value = True
        discovery_result = MagicMock()
        discovery_result.discovery_errors = [("foo", "err")]
        self.diagnostic.discoverer.discover.return_value = discovery_result
        self.diagnostic.runner.failed_modules = []
        self.diagnostic.runner.auto_fixes = []
        self.diagnostic.runner.edges = set()

        result = self.diagnostic.run_diagnostic("foo")
        self.assertFalse(result)

    def test_graph_export(self):
        self.diagnostic.config.graph = True
        self.diagnostic.config.dot_file = "out.dot"
        self.diagnostic.discoverer.validate_package.return_value = True
        discovery_result = MagicMock()
        discovery_result.discovery_errors = []
        self.diagnostic.discoverer.discover.return_value = discovery_result
        self.diagnostic.runner.failed_modules = []
        self.diagnostic.runner.auto_fixes = []
        self.diagnostic.runner.edges = {("a", "b")}

        self.diagnostic.run_diagnostic("foo")
        self.diagnostic.reporter.export_graph.assert_called()

if __name__ == "__main__":
    unittest.main()
