# tests/modules/test_utils_extended.py

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import importlib

from importdoc.modules.utils import (
    _format_evidence_item,
    analyze_ast_symbols,
    find_import_usages_in_repo,
    find_module_file_path,
    find_similar_modules,
    find_symbol_definitions_in_repo,
    safe_read_text,
    suggest_pip_names,
)
from importdoc.modules import utils


class TestUtilsExtended(unittest.TestCase):
    def test_find_similar_modules(self):
        # Create a dummy project structure
        root = Path("dummy_project")
        (root / "my_package" / "my_module").mkdir(parents=True, exist_ok=True)
        (root / "my_package" / "another_module.py").touch()
        (root / "my_package" / "my_mod.py").touch()

        # Test finding similar modules
        similar = find_similar_modules(root, "my_package.my_module")
        self.assertIn(("my_package.my_mod", 0.9), [(s[0], round(s[1], 1)) for s in similar])

        # Clean up the dummy project structure
        import shutil
        shutil.rmtree(root)

    def test_format_evidence_item(self):
        # Test with a relative path
        path = Path("my_package/my_module.py")
        result = _format_evidence_item(path, 10, "class")
        self.assertEqual(result, "my_package/my_module.py:10: class")

        # Test with an absolute path that is inside CWD
        # If CWD is /app, then /app/my_package/my_module.py is relative to CWD
        cwd = Path.cwd()
        path = cwd / "my_package/my_module.py"
        result = _format_evidence_item(path, 10, "class")
        self.assertEqual(result, "my_package/my_module.py:10: class")

        # Test with an absolute path that is outside CWD
        # Assuming /tmp is outside /app (or whatever CWD is)
        path = Path("/tmp/my_package/my_module.py")
        result = _format_evidence_item(path, 10, "class")
        self.assertEqual(result, "/tmp/my_package/my_module.py:10: class")

    def test_safe_read_text_encoding_error(self):
        path = Path("test_encoding.txt")
        path.write_bytes(b"\xff\xfe")  # Invalid UTF-8 sequence

        # Mock to fail on utf-8, succeed on latin-1
        with patch("pathlib.Path.read_text", side_effect=[UnicodeDecodeError("utf-8", b"", 0, 1, "reason"), "latin-1 content"]) as mock_read_text:
            content = safe_read_text(path)
            self.assertEqual(content, "latin-1 content")
            self.assertEqual(mock_read_text.call_count, 2)
            self.assertEqual(mock_read_text.call_args_list[0].kwargs['encoding'], 'utf-8')
            self.assertEqual(mock_read_text.call_args_list[1].kwargs['encoding'], 'latin-1')

        # Mock to fail on both
        with patch("pathlib.Path.read_text", side_effect=[UnicodeDecodeError("utf-8", b"", 0, 1, "reason"), Exception("some error")]) as mock_read_text:
            content = safe_read_text(path)
            self.assertIsNone(content)
            self.assertEqual(mock_read_text.call_count, 2)

        os.remove("test_encoding.txt")

    def test_analyze_ast_symbols_all_formats_and_errors(self):
        # Test __all__ parsing with a list
        source_code_list = '__all__ = ["ClassA", "function_b"]'
        path = Path("test_all_list.py")
        path.write_text(source_code_list)
        symbols = analyze_ast_symbols(path)
        self.assertEqual(symbols["all"], ["ClassA", "function_b"])
        os.remove(path)

        # Test __all__ parsing with a tuple
        source_code_tuple = '__all__ = ("ClassA", "function_b")'
        path = Path("test_all_tuple.py")
        path.write_text(source_code_tuple)
        symbols = analyze_ast_symbols(path)
        self.assertEqual(symbols["all"], ["ClassA", "function_b"])
        os.remove(path)

        # Test __all__ parsing with unsupported format (non-constant in list)
        source_code_unsupported1 = 'var = "foo"\n__all__ = [var]'
        path = Path("test_all_unsupported1.py")
        path.write_text(source_code_unsupported1)
        symbols = analyze_ast_symbols(path)
        self.assertEqual(symbols["all"], "unsupported")
        os.remove(path)

        # Test __all__ parsing with unsupported format (function call)
        source_code_unsupported2 = '__all__ = some_function()'
        path = Path("test_all_unsupported2.py")
        path.write_text(source_code_unsupported2)
        symbols = analyze_ast_symbols(path)
        self.assertEqual(symbols["all"], "unsupported")
        os.remove(path)

        # Test syntax error
        source_code_syntax_error = 'def my_func('
        path = Path("test_syntax_error.py")
        path.write_text(source_code_syntax_error)
        symbols = analyze_ast_symbols(path)
        self.assertIn("SyntaxError", symbols["error"])
        os.remove(path)

    def test_analyze_ast_symbols_file_read_error(self):
        with patch("importdoc.modules.utils.safe_read_text", return_value=None):
            symbols = analyze_ast_symbols(Path("non_existent_file.py"))
            self.assertEqual(symbols["error"], "Could not read file.")

    @patch("importlib.util.find_spec", return_value=None)
    @patch("importlib.resources.files", side_effect=Exception("not a package"))
    @patch("sys.path", ["/dummy/path"])
    def test_find_module_file_path_fallback(self, mock_resources_files, mock_find_spec):
        # Test fallback to sys.path scan
        with patch("pathlib.Path.is_file", side_effect=[False, True]):
            path = find_module_file_path("my_module")
            self.assertEqual(path, Path("/dummy/path/my_module.py"))

    @patch("importdoc.modules.utils.importlib_metadata")
    def test_suggest_pip_names_metadata_error(self, mock_importlib_metadata):
        # Test case where importlib_metadata.distributions raises an exception
        mock_importlib_metadata.distributions.side_effect = Exception("metadata error")
        names = suggest_pip_names("my_module")
        self.assertEqual(names, ["my_module", "my-module"])


    def test_repo_scan_functions_no_root(self):
        # Test repo scan functions when the project root does not exist
        non_existent_path = Path("/non_existent_path")
        self.assertEqual(find_symbol_definitions_in_repo(non_existent_path, "symbol"), [])
        self.assertEqual(find_import_usages_in_repo(non_existent_path, "symbol"), [])

    def test_find_import_usages_star_import(self):
        # Test find_import_usages_in_repo with a star import
        root = Path("dummy_project")
        (root / "my_package").mkdir(parents=True, exist_ok=True)
        (root / "my_package" / "my_module.py").write_text("from other_module import *")

        results = find_import_usages_in_repo(root, "my_symbol", from_module="other_module")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][2], "star-import from other_module")

        import shutil
        shutil.rmtree(root)

    def test_find_symbol_definitions_max_results(self):
        # Test find_symbol_definitions_in_repo with max_results
        root = Path("dummy_project")
        (root / "my_package").mkdir(parents=True, exist_ok=True)
        (root / "my_package" / "my_module.py").write_text("my_symbol = 1\nmy_symbol = 2")

        with patch("pathlib.Path.rglob") as mock_rglob:
            mock_rglob.return_value = [Path("dummy_project/my_package/my_module.py")]
            with patch("importdoc.modules.utils.safe_read_text", return_value="my_symbol = 1\nmy_symbol = 2"):
                results = find_symbol_definitions_in_repo(root, "my_symbol", max_results=1)
                self.assertEqual(len(results), 1)

        import shutil
        shutil.rmtree(root)

    def test_find_import_usages_attribute_usage(self):
        # Test find_import_usages_in_repo with attribute usage
        root = Path("dummy_project")
        (root / "my_package").mkdir(parents=True, exist_ok=True)
        (root / "my_package" / "my_module.py").write_text("import my_other_module\nmy_other_module.my_symbol()")

        results = find_import_usages_in_repo(root, "my_symbol")
        self.assertEqual(len(results), 1)
        self.assertIn("attr-usage", results[0][2])

        import shutil
        shutil.rmtree(root)

    def test_find_import_usages_nested_attribute_usage(self):
        # Test find_import_usages_in_repo with nested attribute usage
        root = Path("dummy_project")
        (root / "my_package").mkdir(parents=True, exist_ok=True)
        (root / "my_package" / "my_module.py").write_text("import my_other_module\nmy_other_module.sub_module.my_symbol()")

        results = find_import_usages_in_repo(root, "my_symbol")
        self.assertEqual(len(results), 1)
        self.assertIn("attr-usage", results[0][2])

        import shutil
        shutil.rmtree(root)


class TestUtilsCoverage(unittest.TestCase):
    def test_importlib_metadata_exception(self):
        with patch.dict("sys.modules", {"importlib.metadata": None}):
            importlib.reload(utils)
            self.assertIsNone(utils.importlib_metadata)
        # Restore the module
        importlib.reload(utils)

    def test_safe_read_text_io_error(self):
        path = MagicMock(spec=Path)
        path.read_text.side_effect = IOError
        self.assertIsNone(utils.safe_read_text(path))

    def test_analyze_ast_symbols_unsupported_all(self):
        path = Path("test_unsupported_all.py")
        path.write_text("__all__ = 1")
        result = utils.analyze_ast_symbols(path)
        self.assertEqual(result["all"], "unsupported")
        os.remove(path)

    def test_find_module_file_path_no_origin(self):
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.return_value.origin = None
            self.assertIsNone(utils.find_module_file_path("foo"))

    def test_find_module_file_path_resources_error(self):
        with patch("importlib.resources.files", side_effect=Exception):
            self.assertIsNone(utils.find_module_file_path("foo"))

    def test_find_symbol_definitions_in_repo_ignored_path(self):
        with patch("importdoc.modules.utils._is_ignored_path", return_value=True):
            self.assertEqual(utils.find_symbol_definitions_in_repo(Path("."), "foo"), [])

    def test_find_import_usages_in_repo_ignored_path(self):
        with patch("importdoc.modules.utils._is_ignored_path", return_value=True):
            self.assertEqual(utils.find_import_usages_in_repo(Path("."), "foo"), [])

    def test_find_similar_modules_empty_dir_name(self):
        with patch("pathlib.Path.rglob") as mock_rglob:
            mock_rglob.return_value = [MagicMock(is_dir=lambda: True, name="")]
            self.assertEqual(utils.find_similar_modules(Path("."), "foo"), [])


if __name__ == "__main__":
    unittest.main()
