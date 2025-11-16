# tests/modules/test_cache.py


import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from importdoc.modules.cache import DiagnosticCache


def test_cache_disabled():
    with tempfile.TemporaryDirectory() as temp_dir:
        cache = DiagnosticCache(cache_dir=Path(temp_dir))
        cache.enabled = False
        with tempfile.NamedTemporaryFile(suffix=".py") as temp_file:
            module_path = Path(temp_file.name)
            cache.set("my_module", module_path, {"success": True})
            assert cache.get("my_module", module_path) is None


def test_cache_get_set():
    with tempfile.TemporaryDirectory() as temp_dir:
        cache = DiagnosticCache(cache_dir=Path(temp_dir))
        with tempfile.NamedTemporaryFile(suffix=".py") as temp_file:
            module_path = Path(temp_file.name)
            module_path.write_text("print('hello')")
            result = {"success": True}
            cache.set("my_module", module_path, result)
            cached_result = cache.get("my_module", module_path)
            assert cached_result == result


def test_cache_get_miss():
    with tempfile.TemporaryDirectory() as temp_dir:
        cache = DiagnosticCache(cache_dir=Path(temp_dir))
        with tempfile.NamedTemporaryFile(suffix=".py") as temp_file:
            module_path = Path(temp_file.name)
            assert cache.get("my_module", module_path) is None


def test_cache_get_invalid_json():
    with tempfile.TemporaryDirectory() as temp_dir:
        cache = DiagnosticCache(cache_dir=Path(temp_dir))
        with tempfile.NamedTemporaryFile(suffix=".py") as temp_file:
            module_path = Path(temp_file.name)
            source_hash = cache._get_source_hash(module_path)
            cache_key = cache._get_cache_key("my_module", source_hash)
            cache_file = cache.cache_dir / f"{cache_key}.json"
            cache_file.write_text("invalid json")
            assert cache.get("my_module", module_path) is None


def test_cache_env_var():
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch.dict(
            os.environ, {"IMPORT_DIAGNOSTIC_CACHE_DIR": temp_dir}
        ):
            cache = DiagnosticCache()
            assert cache.cache_dir == Path(temp_dir)


