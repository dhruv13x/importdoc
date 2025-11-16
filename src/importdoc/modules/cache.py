# src/importdoc/modules/cache.py

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional


class DiagnosticCache:
    def __init__(self, cache_dir: Optional[Path] = None):
        # Prefer explicit argument, then explicit env var, then default path.
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        else:
            env_dir = os.environ.get("IMPORT_DIAGNOSTIC_CACHE_DIR")
            if env_dir:
                self.cache_dir = Path(env_dir)
            else:
                self.cache_dir = Path.home() / ".import_diagnostic_cache"

        # Create cache dir
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Fall back to temp dir
            self.cache_dir = Path(tempfile.gettempdir()) / ".import_diagnostic_cache"
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.enabled = True

    def _get_cache_key(self, module_name: str, source_hash: str) -> str:
        return hashlib.sha256(
            f"{module_name}:{source_hash}".encode("utf-8")
        ).hexdigest()

    def _get_source_hash(self, module_path: Path) -> str:
        try:
            content = module_path.read_bytes()
            return hashlib.sha256(content).hexdigest()
        except Exception:
            return ""

    def get(self, module_name: str, module_path: Optional[Path]) -> Optional[Dict]:
        if not self.enabled or not module_path or not module_path.exists():
            return None
        source_hash = self._get_source_hash(module_path)
        if not source_hash:
            return None
        cache_file = (
            self.cache_dir / f"{self._get_cache_key(module_name, source_hash)}.json"
        )
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def set(self, module_name: str, module_path: Optional[Path], result: Dict):
        if not self.enabled or not module_path or not module_path.exists():
            return
        source_hash = self._get_source_hash(module_path)
        if not source_hash:
            return
        cache_file = (
            self.cache_dir / f"{self._get_cache_key(module_name, source_hash)}.json"
        )
        # Atomic write with safe temp_name handling
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=str(self.cache_dir), encoding="utf-8"
            ) as tf:
                temp_name = tf.name
                json.dump(result, tf, indent=2)
                tf.flush()  # Ensure data is written before replace
            os.replace(temp_name, str(cache_file))
        except Exception:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.remove(temp_name)
                except Exception:
                    pass
