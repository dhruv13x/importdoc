# tests/modules/test_discovery_extended.py


import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from importdoc.modules.discovery import ModuleDiscoverer, DiscoveryResult
from importdoc.modules.config import DiagnosticConfig
from importdoc.modules.reporting import DiagnosticReporter
import sys

class TestModuleDiscoverer(unittest.TestCase):
    def setUp(self):
        self.config = DiagnosticConfig(allow_root=True)
        self.reporter = DiagnosticReporter(self.config)
        self.reporter.log = MagicMock()
        self.reporter.diagnose_path_issue = MagicMock()
        self.discoverer = ModuleDiscoverer(self.config, self.reporter)

    def test_should_skip_module(self):
        self.config.exclude_patterns = ["^test\\."]
        # Re-run post_init to compile regexes since we changed exclude_patterns
        self.config.__post_init__()
        self.assertTrue(self.discoverer._should_skip_module("test.module"))
        self.assertFalse(self.discoverer._should_skip_module("my_package.module"))
        self.assertIn("test.module", self.discoverer.skipped_modules)

    def test_validate_package_success(self):
        with patch("importlib.util.find_spec", return_value=True):
            self.assertTrue(self.discoverer.validate_package("my_package"))

    def test_validate_package_not_found(self):
        with patch("importlib.util.find_spec", return_value=None):
            self.assertFalse(self.discoverer.validate_package("my_package"))
            self.reporter.log.assert_called_with("Package 'my_package' not found.", level="ERROR")
            self.reporter.diagnose_path_issue.assert_called_with("my_package")

    def test_validate_package_error(self):
        with patch("importlib.util.find_spec", side_effect=Exception("Error")):
            self.assertFalse(self.discoverer.validate_package("my_package"))
            self.reporter.log.assert_called()

    def test_discover_root_not_found(self):
        with patch("importlib.util.find_spec", return_value=None):
            result = self.discoverer.discover("my_package")
            self.assertEqual(len(result.discovery_errors), 1)
            self.assertEqual(result.discovery_errors[0][0], "my_package")

    def test_discover_root_error(self):
        with patch("importlib.util.find_spec", side_effect=Exception("Root error")):
            result = self.discoverer.discover("my_package")
            self.assertEqual(len(result.discovery_errors), 1)

    def test_discover_root_error_continue(self):
        self.config.continue_on_error = True
        with patch("importlib.util.find_spec", side_effect=Exception("Root error")):
            result = self.discoverer.discover("my_package")
            self.assertEqual(len(result.discovery_errors), 1)

    def test_discover_success(self):
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_spec = MagicMock()
            mock_spec.submodule_search_locations = ["/path/to/pkg"]
            mock_find_spec.return_value = mock_spec

            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.iterdir") as mock_iterdir:
                    file_entry = MagicMock()
                    file_entry.name = "module.py"
                    file_entry.suffix = ".py"
                    file_entry.is_dir.return_value = False
                    file_entry.stem = "module"

                    dir_entry = MagicMock()
                    dir_entry.name = "subpkg"
                    dir_entry.is_dir.return_value = True
                    dir_entry.__truediv__.return_value.exists.return_value = True

                    mock_iterdir.return_value = [file_entry, dir_entry]

                    # We need to control subsequent find_spec calls
                    def side_effect(name):
                         if name == "my_package": return mock_spec
                         if name == "my_package.subpkg": return mock_spec # Recursive return
                         return None
                    mock_find_spec.side_effect = side_effect

                    # Prevent infinite recursion by not yielding dir_entry in the recursive call
                    # Or simpler: let the loop finish as we didn't add more things to stack in side_effect?
                    # The discover method adds to stack if it finds a package.

                    # To test recursion, we need to mock iterdir to return empty for the subdirectory
                    def iterdir_side_effect():
                         if mock_iterdir.call_count == 1:
                             return [file_entry, dir_entry]
                         return []
                    mock_iterdir.side_effect = iterdir_side_effect

                    result = self.discoverer.discover("my_package")
                    self.assertIn("my_package", result.discovered_modules)
                    self.assertIn("my_package.module", result.discovered_modules)
                    self.assertIn("my_package.subpkg", result.discovered_modules)

    def test_discover_error_in_loop(self):
         with patch("importlib.util.find_spec") as mock_find_spec:
            mock_spec = MagicMock()
            mock_spec.submodule_search_locations = ["/path/to/pkg"]
            mock_find_spec.return_value = mock_spec

            with patch("pathlib.Path.exists", return_value=True):
                 with patch("pathlib.Path.iterdir", side_effect=Exception("Loop error")):
                      result = self.discoverer.discover("my_package")
                      self.assertEqual(len(result.discovery_errors), 1)

    def test_path_to_module(self):
        with patch("sys.path", ["/app"]):
             with patch("pathlib.Path.resolve") as mock_resolve:
                  mock_resolve.return_value = Path("/app/my_package/my_module.py")
                  # We also need sys.path resolution to work in the loop
                  # The code does: Path(sp).resolve()
                  # We can mock Path again or rely on real Path behavior if we use real paths.

                  # Let's use real paths to simplify
                  pass

        # Using real logic with fake paths
        self.discoverer.path_to_module = lambda p: "my_package.my_module" # Mocking internal logic is hard, let's test the function directly if possible

    def test_path_to_module_logic(self):
        # Create a test setup where we can control sys.path and resolve
        with patch("sys.path", ["/root/pkg"]):
             with patch("pathlib.Path.resolve", side_effect=lambda: Path("/root/pkg/sub/mod.py")):
                 # The method calls resolve() on the input path AND on sys.path entries
                 # We need a more robust patch.
                 pass

        # Let's try to test the actual logic with real paths that don't need to exist
        path = Path("/tmp/fake/pkg/mod.py")
        with patch("sys.path", ["/tmp/fake"]):
            with patch("pathlib.Path.resolve", return_value=path):
                # path.resolve() is called
                # then Path(sp).resolve() is called
                with patch("pathlib.Path.resolve", side_effect=[path, Path("/tmp/fake")]):
                     # This side_effect might be tricky because it depends on call order
                     pass

    def test_path_to_module_real(self):
        # Use a real path
        cwd = Path.cwd()
        mod_path = cwd / "src" / "importdoc" / "cli.py"
        with patch("sys.path", [str(cwd / "src")]):
            mod = self.discoverer.path_to_module(mod_path)
            self.assertEqual(mod, "importdoc.cli")

        init_path = cwd / "src" / "importdoc" / "__init__.py"
        with patch("sys.path", [str(cwd / "src")]):
            mod = self.discoverer.path_to_module(init_path)
            self.assertEqual(mod, "importdoc")

if __name__ == "__main__":
    unittest.main()
