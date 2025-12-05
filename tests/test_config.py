
import unittest
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import os

# We need to import the CLI main or the parts we want to test
# However, cli.main() runs the whole thing. We want to test config loading.
# Since we haven't implemented the config loader yet, we are writing the test first (RED).
# We assume we will refactor CLI to use a `load_config` function or `Config` class.
# But for now, let's assume we will expose a `load_config` function in a new module `importdoc.config`.
# Or better, we test the behavior of CLI arguments.

from importdoc.cli import main

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)
        self.cwd = os.getcwd()
        os.chdir(self.test_dir.name)
        self.addCleanup(lambda: os.chdir(self.cwd))

    def test_load_config_from_pyproject_toml(self):
        # Create a pyproject.toml
        pyproject_content = """
[tool.importdoc]
max_depth = 42
timeout = 10
"""
        with open("pyproject.toml", "w") as f:
            f.write(pyproject_content)

        # We need to mock sys.argv
        with patch("sys.argv", ["importdoc", "."]), \
             patch("importdoc.cli.ImportDiagnostic") as MockDiagnostic:

            # Run main
            try:
                main()
            except SystemExit:
                pass

            # Check if ImportDiagnostic was called with config values
            # The CLI args (defaults) might override if not handled carefully.
            # If our implementation is correct, config file values should override defaults
            # but be overridden by explicit CLI args.

            # Since we didn't pass --max-depth in CLI, it should take 42 from config.
            # Default max_depth is None or something else (let's check cli.py).
            # In cli.py: `parser.add_argument("--max-depth", type=int, help="Max discovery depth.")`
            # implies default is None.

            args, kwargs = MockDiagnostic.call_args
            self.assertEqual(kwargs['max_depth'], 42)
            self.assertEqual(kwargs['timeout'], 10)

    def test_cli_overrides_config(self):
        # Create a pyproject.toml
        pyproject_content = """
[tool.importdoc]
max_depth = 42
"""
        with open("pyproject.toml", "w") as f:
            f.write(pyproject_content)

        # Run with explicit --max-depth 100
        with patch("sys.argv", ["importdoc", ".", "--max-depth", "100"]), \
             patch("importdoc.cli.ImportDiagnostic") as MockDiagnostic:

            try:
                main()
            except SystemExit:
                pass

            args, kwargs = MockDiagnostic.call_args
            self.assertEqual(kwargs['max_depth'], 100)
