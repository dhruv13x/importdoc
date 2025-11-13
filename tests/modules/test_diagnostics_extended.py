import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import re
from importdoc.modules.diagnostics import ImportDiagnostic

class TestDiagnosticsExtended(unittest.TestCase):
    def test_should_skip_module(self):
        # Test with no exclude patterns
        diagnostic = ImportDiagnostic(allow_root=True)
        self.assertFalse(diagnostic._should_skip_module("my_module"))
        self.assertEqual(len(diagnostic.skipped_modules), 0)

        # Test with an exclude pattern that matches
        diagnostic = ImportDiagnostic(exclude_patterns=["^_private"], allow_root=True)
        self.assertTrue(diagnostic._should_skip_module("_private_module"))
        self.assertIn("_private_module", diagnostic.skipped_modules)

        # Test with an exclude pattern that does not match
        self.assertFalse(diagnostic._should_skip_module("public_module"))
        self.assertNotIn("public_module", diagnostic.skipped_modules)

    @patch("importlib.util.find_spec")
    def test_validate_package(self, mock_find_spec):
        diagnostic = ImportDiagnostic(allow_root=True)

        # Test case 1: Package is found
        mock_find_spec.return_value = MagicMock()
        self.assertTrue(diagnostic._validate_package("existing_package"))

        # Test case 2: Package is not found
        mock_find_spec.return_value = None
        with patch.object(diagnostic, '_diagnose_path_issue') as mock_diagnose:
            self.assertFalse(diagnostic._validate_package("non_existing_package"))
            mock_diagnose.assert_called_once_with("non_existing_package")

        # Test case 3: find_spec raises an exception
        mock_find_spec.side_effect = Exception("test error")
        with patch.object(diagnostic, '_diagnose_path_issue') as mock_diagnose:
            self.assertFalse(diagnostic._validate_package("error_package"))
            mock_diagnose.assert_called_once_with("error_package")

    @patch("importlib.util.find_spec")
    def test_discover_all_modules_no_submodules(self, mock_find_spec):
        diagnostic = ImportDiagnostic(allow_root=True)
        mock_spec = MagicMock()
        mock_spec.submodule_search_locations = None
        mock_find_spec.return_value = mock_spec

        diagnostic._discover_all_modules("my_package")
        self.assertIn("my_package", diagnostic.discovered_modules)
        self.assertEqual(len(diagnostic.discovered_modules), 1)

    @patch("importlib.util.find_spec", return_value=None)
    @patch("sys.path", [])
    def test_run_diagnostic_with_package_dir(self, mock_find_spec):
        diagnostic = ImportDiagnostic(allow_root=True)
        with patch.object(diagnostic, '_diagnose_path_issue'):
            result = diagnostic.run_diagnostic("my_package", "/tmp/my_package")
            self.assertFalse(result)

    @patch("importdoc.modules.diagnostics.ImportDiagnostic._log")
    def test_print_header(self, mock_log):
        diagnostic = ImportDiagnostic(allow_root=True)
        diagnostic._print_header("my_package", "/tmp/my_package")

        # Check that the log was called with the correct information
        self.assertTrue(any("Target package: my_package" in call[0][0] for call in mock_log.call_args_list))
        self.assertTrue(any("Package dir: /tmp/my_package" in call[0][0] for call in mock_log.call_args_list))

    @patch("importdoc.modules.diagnostics.find_module_file_path")
    @patch("importdoc.modules.diagnostics.ImportDiagnostic._log")
    def test_diagnose_path_issue(self, mock_log, mock_find_module_file_path):
        diagnostic = ImportDiagnostic(allow_root=True)

        # Test case 1: File path is found
        mock_path = MagicMock()
        mock_path.stat.return_value.st_mode = 0o755
        mock_find_module_file_path.return_value = mock_path

        diagnostic._diagnose_path_issue("my_module")

        self.assertTrue(any("Found file:" in call[0][0] for call in mock_log.call_args_list))
        self.assertTrue(any("Permissions: 755" in call[0][0] for call in mock_log.call_args_list))

        # Test case 2: File path is not found
        mock_log.reset_mock()
        mock_find_module_file_path.return_value = None
        diagnostic._diagnose_path_issue("my_module")
        self.assertTrue(any("No file found matching module." in call[0][0] for call in mock_log.call_args_list))

if __name__ == "__main__":
    unittest.main()
