import unittest
from importdoc.modules.diagnostics import ImportDiagnostic

class TestDiagnostics(unittest.TestCase):
    def test_import_diagnostic_init(self):
        diagnostic = ImportDiagnostic()
        self.assertIsNotNone(diagnostic)

    def test_run_diagnostic_success(self):
        diagnostic = ImportDiagnostic()
        success = diagnostic.run_diagnostic("os")
        self.assertTrue(success)

    def test_run_diagnostic_failure(self):
        diagnostic = ImportDiagnostic()
        success = diagnostic.run_diagnostic("non_existent_module")
        self.assertFalse(success)

if __name__ == "__main__":
    unittest.main()
