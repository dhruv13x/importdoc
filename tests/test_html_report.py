
import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock
from importdoc.modules.diagnostics import ImportDiagnostic
from importdoc.modules.discovery import DiscoveryResult

class TestHTMLReport(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)
        self.cwd = os.getcwd()
        os.chdir(self.test_dir.name)
        self.addCleanup(lambda: os.chdir(self.cwd))

    def test_html_report_generation(self):
        # We test ImportDiagnostic directly to avoid CLI/sys.path complexity in test environment

        with patch("importdoc.modules.diagnostics.ModuleDiscoverer") as MockDisc, \
             patch("importdoc.modules.diagnostics.ImportRunner") as MockRunner:

            # Setup mocks
            mock_disc_instance = MockDisc.return_value
            mock_disc_instance.validate_package.return_value = True
            mock_disc_instance.discover.return_value = DiscoveryResult(
                discovered_modules={"mypkg", "mypkg.sub"},
                package_tree={"mypkg": ["mypkg.sub"]},
                discovery_errors=[],
                skipped_modules=set()
            )

            mock_runner_instance = MockRunner.return_value
            mock_runner_instance.failed_modules = []
            mock_runner_instance.imported_modules = {"mypkg"}
            mock_runner_instance.edges = {("mypkg", "os"), ("mypkg", "sys"), ("mypkg", "mypkg.sub")}
            mock_runner_instance.timings = {}
            mock_runner_instance.auto_fixes = []

            # Run diagnostic with html=True
            diag = ImportDiagnostic(html=True, dry_run=True, verbose=True)
            success = diag.run_diagnostic("mypkg")

            self.assertTrue(success, "Diagnostic run should be successful")

            # Verify report file exists
            expected_file = "mypkg_report.html"
            self.assertTrue(os.path.exists(expected_file), f"HTML Report {expected_file} should be generated")

            with open(expected_file, "r") as f:
                content = f.read()
                self.assertIn("<!DOCTYPE html>", content)
                self.assertIn("mypkg", content)
                self.assertIn("mypkg.sub", content)
