# tests/modules/test_analysis_extended.py


import unittest
import sys
from unittest.mock import MagicMock, patch
from pathlib import Path
from importdoc.modules.analysis import ErrorAnalyzer, _format_evidence_item
from importdoc.modules.config import DiagnosticConfig

class TestErrorAnalyzer(unittest.TestCase):
    def setUp(self):
        self.config = DiagnosticConfig(allow_root=True)
        self.analyzer = ErrorAnalyzer(self.config)

    def test_analyze_no_module_named_standard_library(self):
        error = ImportError("No module named 'os.path'")
        with patch("importdoc.modules.analysis.find_module_file_path", return_value=None):
            # We need importlib.util.find_spec to NOT find the parent 'os', otherwise it thinks it's a local submodule
            with patch("importlib.util.find_spec", return_value=None):
                with patch("importdoc.modules.analysis.is_standard_lib", return_value=True):
                     context = self.analyzer.analyze("os.path", error, None, Path("."), None, [])
        self.assertEqual(context["type"], "standard_library")

    def test_analyze_no_module_named_external_dependency(self):
        error = ImportError("No module named 'requests'")
        with patch("importdoc.modules.analysis.find_module_file_path", return_value=None):
            with patch("importdoc.modules.analysis.is_standard_lib", return_value=False):
                with patch("importdoc.modules.analysis.suggest_pip_names", return_value=["requests"]):
                    context = self.analyzer.analyze("requests", error, None, Path("."), None, [])
        self.assertEqual(context["type"], "external_dependency")
        self.assertIn("pip install requests", context["suggestions"])

    def test_analyze_cannot_import_name_circular(self):
        error = ImportError("cannot import name 'foo' from 'bar'")
        with patch("importdoc.modules.analysis.find_module_file_path", return_value=Path("bar.py")):
             with patch("importdoc.modules.analysis.analyze_ast_symbols", return_value={"functions": {"foo"}}):
                 context = self.analyzer.analyze("bar", error, None, Path("."), None, ["baz"])
        self.assertIn("'foo' exists in bar.py! Likely circular import.", context["evidence"])

    def test_analyze_circular_import_error(self):
         error = ImportError("circular import detected")
         context = self.analyzer.analyze("foo", error, None, Path("."), None, ["bar"])
         self.assertEqual(context["type"], "circular_import")

    def test_analyze_shared_library_error(self):
        error = ImportError("dll load failed")
        context = self.analyzer.analyze("foo", error, None, Path("."), None, [])
        self.assertEqual(context["type"], "shared_library")

    def test_parse_tb_for_import_success(self):
        tb_str = 'File "test.py", line 1, in <module>\n    from foo import bar'
        with patch("importdoc.modules.analysis.safe_read_text", return_value="from foo import bar"):
             result = self.analyzer.parse_tb_for_import(tb_str, "ImportError")
        self.assertEqual(result["module"], "foo")
        self.assertEqual(result["symbols"], ["bar"])

    def test_parse_tb_for_import_no_tb(self):
        result = self.analyzer.parse_tb_for_import(None, "ImportError")
        self.assertIsNone(result)

    def test_calculate_confidence(self):
        context = {
            "evidence": ["class foo", "from-import bar"],
            "suggestions": ["Possible correct import"],
            "similar_modules": ["baz"]
        }
        with patch("importdoc.modules.confidence.ConfidenceCalculator.calculate", return_value=(80, "High")):
            confidence, label = self.analyzer.calculate_confidence(context)
        self.assertEqual(confidence, 80)
        self.assertEqual(label, "High")

    def test_analyze_no_module_named_local_submodule(self):
        error = ImportError("No module named 'my_pkg.sub'")
        with patch("importdoc.modules.analysis.find_module_file_path", return_value=None):
             with patch("importlib.util.find_spec", return_value=True):
                 context = self.analyzer.analyze("my_pkg.sub", error, None, Path("."), None, [])
        self.assertEqual(context["type"], "local_submodule")

    def test_analyze_parent_check_exception(self):
        error = ImportError("No module named 'my_pkg.sub'")
        with patch("importdoc.modules.analysis.find_module_file_path", return_value=None):
             with patch("importlib.util.find_spec", side_effect=Exception("oops")):
                 context = self.analyzer.analyze("my_pkg.sub", error, None, Path("."), None, [])
        self.assertIn("Failed to check parent module", str(context["evidence"]))

    def test_analyze_module_exists_and_perms(self):
        error = ImportError("No module named 'requests'")
        mock_path = MagicMock(spec=Path)
        mock_path.stat.return_value.st_mode = 0o755
        mock_path.__str__.return_value = "/path/to/requests.py"

        with patch("importdoc.modules.analysis.find_module_file_path", return_value=mock_path):
             context = self.analyzer.analyze("requests", error, None, Path("."), None, [])

        self.assertTrue(any("Module file exists" in e for e in context["evidence"]))
        self.assertTrue(any("Permissions: 755" in e for e in context["evidence"]))

    def test_analyze_module_exists_perms_error(self):
        error = ImportError("No module named 'requests'")
        mock_path = MagicMock(spec=Path)
        mock_path.stat.side_effect = Exception("stat error")

        with patch("importdoc.modules.analysis.find_module_file_path", return_value=mock_path):
             context = self.analyzer.analyze("requests", error, None, Path("."), None, [])

        self.assertTrue(any("Module file exists" in e for e in context["evidence"]))

    def test_parse_tb_for_import_fallback(self):
        # Test fallback when AST parsing fails or node not found in AST but present in text
        tb_str = 'File "test.py", line 2, in <module>\n    from foo import (bar, baz)'
        file_content = "invalid syntax but the line is here\nfrom foo import (bar, baz)"

        with patch("importdoc.modules.analysis.safe_read_text", return_value=file_content):
            # Patch ast.parse to raise SyntaxError
            with patch("ast.parse", side_effect=SyntaxError):
                result = self.analyzer.parse_tb_for_import(tb_str, "ImportError")

        self.assertEqual(result["module"], "foo")
        self.assertEqual(result["symbols"], ["bar", "baz"])

    def test_parse_tb_for_import_multiline_fuzzy(self):
        # Test fuzzy matching of line numbers
        tb_str = 'File "test.py", line 12, in <module>\n    from foo import bar'
        # The import is actually at line 10
        file_content = "\n" * 9 + "from foo import bar"

        with patch("importdoc.modules.analysis.safe_read_text", return_value=file_content):
            result = self.analyzer.parse_tb_for_import(tb_str, "ImportError")

        self.assertEqual(result["module"], "foo")
        self.assertEqual(result["symbols"], ["bar"])
        self.assertEqual(result["line_num"], 12)

    def test_analyze_no_module_named_local_module(self):
        error = ImportError("No module named 'current.missing'")
        with patch("importdoc.modules.analysis.find_module_file_path", return_value=None):
             with patch("importlib.util.find_spec", return_value=None):
                 context = self.analyzer.analyze("current.missing", error, None, Path("."), "current", [])
        self.assertEqual(context["type"], "local_module")

    def test_analyze_cannot_import_name_repo_scan(self):
        error = ImportError("cannot import name 'foo' from 'bar'")
        with patch("importdoc.modules.analysis.find_module_file_path", return_value=Path("bar.py")):
             with patch("importdoc.modules.analysis.analyze_ast_symbols", return_value={}):
                 with patch("importdoc.modules.analysis.find_symbol_definitions_in_repo", return_value=[(Path("baz.py"), 10, "function")]):
                      with patch("pathlib.Path.resolve", return_value=Path("/app/baz.py")):
                           with patch("pathlib.Path.relative_to", return_value=Path("baz.py")):
                               context = self.analyzer.analyze("bar", error, None, Path("."), None, [])

        # Check if suggestions contain the discovered module
        found_suggestion = any("from baz import foo" in s for s in context["suggestions"])
        self.assertTrue(found_suggestion)

    def test_uncovered_branches(self):
        # Test for _format_evidence_item exception
        with patch("pathlib.Path.cwd", side_effect=Exception("cwd error")):
            result = _format_evidence_item(Path("/nonexistent/path"), 1, "kind")
        self.assertIn("/nonexistent/path", result)

        # Test for analyze with no module named and no match
        error = ModuleNotFoundError("no module named 'foo'")
        context = self.analyzer.analyze("foo", error, None, Path("."), None, [])
        self.assertEqual(context["type"], "external_dependency")

        # Test for analyze with cannot import name and ast error
        with patch("importdoc.modules.analysis.find_module_file_path", return_value=Path("file.py")):
            with patch("importdoc.modules.analysis.analyze_ast_symbols", return_value={"error": "some error"}):
                error = ImportError("cannot import name 'bar' from 'foo'")
                context = self.analyzer.analyze("foo", error, None, Path("."), None, [])
        self.assertIn("AST error: some error", context["evidence"])

        # Test for analyze with cannot import name and __all__
        with patch("importdoc.modules.analysis.find_module_file_path", return_value=Path("file.py")):
            with patch("importdoc.modules.analysis.analyze_ast_symbols", return_value={"all": ["bar"]}):
                error = ImportError("cannot import name 'foo' from 'bar'")
                context = self.analyzer.analyze("bar", error, None, Path("."), None, [])
        self.assertIn("__all__: ['bar']", context["evidence"])

        # Test for analyze with repo scan fails
        with patch("importdoc.modules.analysis.find_symbol_definitions_in_repo", side_effect=Exception("scan failed")):
            error = ImportError("cannot import name 'foo' from 'bar'")
            context = self.analyzer.analyze("bar", error, None, Path("."), None, [])
        self.assertIn("Repo scan failed: scan failed (tool continued safely)", context["evidence"])

        # Test for analyze with finds usages
        with patch("importdoc.modules.analysis.find_import_usages_in_repo", return_value=[(Path("file.py"), 1, "from-import")]):
            error = ImportError("cannot import name 'foo' from 'bar'")
            context = self.analyzer.analyze("bar", error, None, Path("."), None, [])
        self.assertIn("file.py:1: from-import", context["evidence"])


if __name__ == "__main__":
    unittest.main()
