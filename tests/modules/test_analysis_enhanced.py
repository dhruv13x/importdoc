
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from importdoc.modules.analysis import ErrorAnalyzer
from importdoc.modules.config import DiagnosticConfig

class TestErrorAnalyzerEnhanced(unittest.TestCase):
    def setUp(self):
        self.config = DiagnosticConfig(allow_root=True)
        self.analyzer = ErrorAnalyzer(self.config)

    def test_analyze_attribute_error_shadowing_stdlib(self):
        # Scenario: User has a local 'math.py' which shadows stdlib 'math'.
        # Error: AttributeError: module 'math' has no attribute 'sqrt'
        # (because local math.py doesn't have it)

        error = AttributeError("module 'math' has no attribute 'sqrt'")

        # We need to simulate that 'math' is a standard library module
        # AND that we found a local file for it.

        with patch("importdoc.modules.analysis.find_module_file_path", return_value=Path("math.py")):
            with patch("importdoc.modules.analysis.is_standard_lib", return_value=True):
                 context = self.analyzer.analyze("math", error, None, Path("."), None, [])

        self.assertEqual(context["type"], "shadowing_stdlib")
        self.assertTrue(any("Shadows standard library module 'math'" in e for e in context["evidence"]))
        self.assertIn("Rename your local file 'math.py' to avoid conflict", context["suggestions"])

    def test_analyze_cannot_import_name_typo(self):
        # Scenario: from foo import bar_func (but it is defined as barfunc)
        error = ImportError("cannot import name 'bar_func' from 'foo'")

        # Mock finding foo.py
        with patch("importdoc.modules.analysis.find_module_file_path", return_value=Path("foo.py")):
             # Mock AST symbols in foo.py to include 'barfunc'
             with patch("importdoc.modules.analysis.analyze_ast_symbols", return_value={"functions": {"barfunc"}, "classes": set(), "assigns": set()}):
                 # We disable repo search to focus on AST fuzzy match
                 with patch("importdoc.modules.analysis.find_symbol_definitions_in_repo", return_value=[]):
                    with patch("importdoc.modules.analysis.find_import_usages_in_repo", return_value=[]):
                        context = self.analyzer.analyze("foo", error, None, Path("."), None, [])

        self.assertIn("Did you mean 'barfunc'?", context["suggestions"])
        self.assertEqual(context["type"], "missing_name")

    def test_analyze_attribute_error_generic(self):
        # Scenario: Just a normal AttributeError not due to shadowing
        error = AttributeError("module 'foo' has no attribute 'bar'")

        with patch("importdoc.modules.analysis.find_module_file_path", return_value=Path("foo.py")):
             with patch("importdoc.modules.analysis.is_standard_lib", return_value=False):
                 context = self.analyzer.analyze("foo", error, None, Path("."), None, [])

        # Should be identified but maybe not shadowing
        self.assertEqual(context["type"], "attribute_error")
        self.assertIn("Check if 'bar' is defined in 'foo'", context["suggestions"])
