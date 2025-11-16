# tests/modules/test_utils.py


import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from importdoc.modules.utils import (
    _is_ignored_path,
    detect_env,
    find_import_usages_in_repo,
    find_module_file_path,
    find_symbol_definitions_in_repo,
    is_standard_lib,
    suggest_pip_names,
)

TEMP_FILE_CONTENT = """
import os
from sys import version

class MyClass:
    pass

def my_function():
    pass

my_variable = 1

__all__ = ["MyClass", "my_function"]
"""


def create_temp_file(content: str, directory: Path) -> Path:
    temp_file = directory / "temp_test_file.py"
    temp_file.write_text(content)
    return temp_file


def test_find_module_file_path():
    # Test with a standard library module
    path = find_module_file_path("os")
    assert path is not None
    assert path.name == "os.py"

    # Test with a non-existent module
    path = find_module_file_path("non_existent_module")
    assert path is None


def test_suggest_pip_names():
    # Test with a simple module name
    names = suggest_pip_names("my_module")
    assert "my-module" in names
    assert "my_module" in names

    # Test with a module name that has a dot
    names = suggest_pip_names("my.module")
    assert "my" in names
    assert "my" in names


def test_is_standard_lib():
    # Test with a standard library module
    assert is_standard_lib("os") is True
    assert is_standard_lib("sys") is True

    # Test with a non-standard library module
    assert is_standard_lib("pytest") is False
    assert is_standard_lib("non_existent_module") is False


def test_detect_env():
    # Test in a non-virtualenv environment
    with patch.object(sys, "prefix", "/usr"):
        with patch.object(sys, "base_prefix", "/usr"):
            env = detect_env()
            assert env["virtualenv"] is False

    # Test in a virtualenv environment
    with patch.object(sys, "prefix", "/home/user/.venv"):
        with patch.object(sys, "base_prefix", "/usr"):
            env = detect_env()
            assert env["virtualenv"] is True


def test_is_ignored_path():
    # Test with an ignored path
    assert _is_ignored_path(Path("/home/user/.venv/lib/python3.9/site-packages")) is True
    assert _is_ignored_path(Path("/home/user/project/.git/hooks")) is True
    assert _is_ignored_path(Path("/home/user/project/build/lib")) is True

    # Test with a non-ignored path
    assert _is_ignored_path(Path("/home/user/project/src/main.py")) is False


def test_find_symbol_definitions_in_repo():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        temp_file = create_temp_file(TEMP_FILE_CONTENT, temp_dir_path)
        # Test with a class
        results = find_symbol_definitions_in_repo(temp_dir_path, "MyClass")
        assert len(results) == 1
        assert results[0][0] == temp_file
        assert results[0][1] == 5
        assert results[0][2] == "class"

        # Test with a function
        results = find_symbol_definitions_in_repo(temp_dir_path, "my_function")
        assert len(results) == 1
        assert results[0][0] == temp_file
        assert results[0][1] == 8
        assert results[0][2] == "function"

        # Test with a variable
        results = find_symbol_definitions_in_repo(temp_dir_path, "my_variable")
        assert len(results) == 1
        assert results[0][0] == temp_file
        assert results[0][1] == 11
        assert results[0][2] == "assign"


def test_find_import_usages_in_repo():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        temp_file = create_temp_file(TEMP_FILE_CONTENT, temp_dir_path)
        # Test with a standard library module
        results = find_import_usages_in_repo(temp_dir_path, "os")
        assert len(results) == 1
        assert results[0][0] == temp_file
        assert results[0][1] == 2
        assert "import os" in results[0][2]

        # Test with a specific symbol from a module
        results = find_import_usages_in_repo(
            temp_dir_path, "version", from_module="sys"
        )
        assert len(results) == 1
        assert results[0][0] == temp_file
        assert results[0][1] == 3
        assert "from-import sys import version" in results[0][2]
