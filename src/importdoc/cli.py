#!/usr/bin/env python3
"""
# importdoc.py
Advanced Import Diagnostic Tool V20 — PRODUCTION
- Cross-platform timeouts
- Explicit JSON-schema handling and optional enforcement
- Atomic cache writes
- Clear safe-mode behavior (does not silently flip CLI flags)
- Telemetry durations normalized to milliseconds
- Graph export correctness and safe file writes
- Improved logging (deduplicated handlers, timestamps)
- Enhanced: Fuzzy module search for missing modules, incomplete import detection
- NEW: Enhanced diagnosis for "no module named" by parsing import symbols from AST and suggesting correct paths based on symbol definitions
"""

from __future__ import annotations

import argparse
import ast
import builtins
import concurrent.futures
import difflib  # New: for fuzzy matching
import hashlib
import importlib
import importlib.resources
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import traceback
from collections import defaultdict
from dataclasses import asdict, dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from tqdm import tqdm
except Exception:
    tqdm = None

try:
    import jsonschema
except Exception:
    jsonschema = None

try:
    import importlib.metadata as importlib_metadata
except Exception:
    importlib_metadata = None

__version__ = (
    "1.0.0"  # Enhanced version for better diagnosis
)

# ----------
# JSON schemas
# ----------
JSON_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "version": {"type": "string"},
        "package": {"type": "string"},
        "discovered_modules": {"type": "array", "items": {"type": "string"}},
        "discovery_errors": {"type": "array", "items": {"type": "object"}},
        "imported_modules": {"type": "array", "items": {"type": "string"}},
        "failed_modules": {"type": "array", "items": {"type": "object"}},
        "skipped_modules": {"type": "array", "items": {"type": "string"}},
        "timings": {"type": "object"},
        "module_tree": {"type": "object"},
        "env_info": {"type": "object"},
        "elapsed_seconds": {"type": "number"},
        "auto_fixes": {"type": "array", "items": {"type": "object"}},
        "telemetry": {"anyOf": [{"type": "object"}, {"type": "null"}]},
        "health_check": {"type": "object"},
    },
    "required": ["version", "package", "health_check"],
}

FIXES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "issue_type": {"type": "string"},
            "module_name": {"type": "string"},
            "confidence": {"type": "number"},
            "description": {"type": "string"},
            "patch": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "manual_steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["issue_type", "module_name", "confidence", "description"],
    },
}


def validate_json(data: Any, schema: Dict) -> bool:
    """Validate JSON if jsonschema installed or environment requests enforcement."""
    enforce = os.environ.get("IMPORT_DIAGNOSTIC_ENFORCE_JSONSCHEMA", "") == "1"
    if jsonschema is None:
        if enforce:
            raise RuntimeError(
                "IMPORT_DIAGNOSTIC_ENFORCE_JSONSCHEMA=1 but 'jsonschema' package is not installed."
            )
        logging.getLogger("import_diagnostic").warning(
            "jsonschema not installed — skipping output validation. Set IMPORT_DIAGNOSTIC_ENFORCE_JSONSCHEMA=1 to require it."
        )
        return True
    try:
        jsonschema.validate(instance=data, schema=schema)
        return True
    except jsonschema.exceptions.ValidationError as e:
        logging.getLogger("import_diagnostic").warning(f"JSON validation failed: {e}")
        if enforce:
            raise
        return False


# ----------
# Telemetry
# ----------
@dataclass
class DiagnosticEvent:
    timestamp: float
    event_type: str
    module_name: str
    duration_ms: float
    metadata: Dict[str, Any]


class TelemetryCollector:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.events: List[DiagnosticEvent] = []
        self._lock = threading.Lock()

    def record(self, event_type: str, module_name: str, duration_ms: float, **metadata):
        if not self.enabled:
            return
        with self._lock:
            self.events.append(
                DiagnosticEvent(
                    timestamp=time.time(),
                    event_type=event_type,
                    module_name=module_name,
                    duration_ms=duration_ms,
                    metadata=metadata,
                )
            )

    def export_json(self) -> str:
        with self._lock:
            return json.dumps([asdict(e) for e in self.events], indent=2)

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self.events)
            by_type = defaultdict(int)
            import_times = []
            for e in self.events:
                by_type[e.event_type] += 1
                if e.event_type in ("import_success", "import_failure"):
                    import_times.append(e.duration_ms)
            avg = (sum(import_times) / len(import_times)) if import_times else 0.0
            slowest = sorted(
                [e for e in self.events if e.event_type == "import_success"],
                key=lambda e: e.duration_ms,
                reverse=True,
            )[:5]
            return {
                "total_events": total,
                "by_type": dict(by_type),
                "avg_import_time_ms": avg,
                "slowest_imports": [
                    {"module": e.module_name, "duration_ms": e.duration_ms}
                    for e in slowest
                ],
            }


# ----------
# AutoFix & generators
# ----------
@dataclass
class AutoFix:
    issue_type: str
    module_name: str
    confidence: float
    description: str
    patch: Optional[str]
    manual_steps: List[str]


class FixGenerator:
    @staticmethod
    def generate_missing_import_fix(
        from_module: str, symbol: str, correct_module: str
    ) -> AutoFix:
        original = f"from {from_module} import {symbol}"
        fixed = f"from {correct_module} import {symbol}"
        patch = f"""--- a/module.py
+++ b/module.py
@@ -1,1 +1,1 @@
-{original}
+{fixed}
"""
        return AutoFix(
            issue_type="missing_import",
            module_name=from_module,
            confidence=0.85,
            description=f"Replace incorrect import path '{from_module}' with '{correct_module}'",
            patch=patch,
            manual_steps=[
                f"Update import: {original} → {fixed}",
                "Run tests to verify fix",
                "Check for other occurrences in codebase",
            ],
        )

    @staticmethod
    def generate_circular_import_fix(cycle: List[str]) -> AutoFix:
        return AutoFix(
            issue_type="circular_import",
            module_name=" -> ".join(cycle),
            confidence=0.70,
            description=f"Circular import detected: {' -> '.join(cycle)}",
            patch=None,
            manual_steps=[
                "Move shared code to a separate module",
                "Use lazy imports (import inside function)",
                "Restructure modules to create a DAG",
                "Consider using dependency injection",
            ],
        )

    @staticmethod
    def generate_missing_dependency_fix(package: str, suggested_pip: str) -> AutoFix:
        return AutoFix(
            issue_type="missing_dependency",
            module_name=package,
            confidence=0.95,
            description=f"Missing external dependency: {package}",
            patch=None,
            manual_steps=[
                f"Install package: pip install {suggested_pip}",
                "Add to requirements.txt",
                "Verify version compatibility",
            ],
        )


# ----------
# Confidence Calculator
# ----------
class ConfidenceCalculator:
    WEIGHTS = {
        "ast_definition": 3.0,
        "ast_usage": 2.0,
        "regex_match": 1.0,
        "syspath_resolvable": 2.5,
        "multiple_sources": 1.5,
        "exact_match": 2.0,
        "fuzzy_match": 1.5,  # New: for similar modules
    }

    @staticmethod
    def calculate(evidence: Dict[str, int], total_suggestions: int) -> Tuple[int, str]:
        raw = 0.0
        parts = []
        for k, count in evidence.items():
            w = ConfidenceCalculator.WEIGHTS.get(k, 1.0)
            raw += w * count
            if count:
                parts.append(f"{count}x {k} ({w})")
        suggestion_bonus = min(total_suggestions * 0.5, 2.0)
        raw += suggestion_bonus
        score = int(round(max(0, min(10, raw))))
        explanation = f"Based on: {', '.join(parts)}"
        if suggestion_bonus:
            explanation += f" + {total_suggestions} actionable suggestions"
        return score, explanation


# ----------
# Cache (atomic writes) — fixed env empty-string bug & temp_name safety
# ----------
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
            # Fall back to home
            self.cache_dir = Path.home() / ".import_diagnostic_cache"
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


# ----------
# Worker: run imports in a short-lived subprocess (strict timeout)
# ----------
def import_module_worker(module_name: str, timeout: Optional[int]) -> Dict[str, Any]:
    """
    Run the import in a subprocess using sys.executable and return structured result.
    Guarantees that a long-running or blocking C-extension won't hang the parent process.
    """
    child_code = (
        "import time, importlib, json, traceback, sys\n"
        "start=time.time()\n"
        "try:\n"
        f"    importlib.import_module({module_name!r})\n"
        "    end=time.time()\n"
        "    res={'success':True,'error':None,'tb':None,'time_ms':(end-start)*1000.0}\n"
        "except Exception:\n"
        "    end=time.time()\n"
        "    res={'success':False,'error':str(sys.exc_info()[1]),'tb':traceback.format_exc(),'time_ms':(end-start)*1000.0}\n"
        "sys.stdout.write(json.dumps(res))\n"
    )

    args = [sys.executable, "-c", child_code]
    start = time.time()
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout if timeout and timeout > 0 else None,
            check=False,
        )
        end = time.time()
        stdout = proc.stdout.decode("utf-8", errors="replace").strip()
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        # Try to parse JSON from stdout
        try:
            parsed = json.loads(stdout) if stdout else None
        except Exception:
            parsed = None

        if parsed and isinstance(parsed, dict) and "success" in parsed:
            # child already reports time_ms; but if missing, use measured
            if "time_ms" not in parsed:
                parsed["time_ms"] = (end - start) * 1000.0
            return {
                "success": parsed.get("success", False),
                "error": parsed.get("error"),
                "tb": parsed.get("tb"),
                "time_ms": parsed.get("time_ms", (end - start) * 1000.0),
            }
        else:
            # Child didn't return the expected JSON — treat as failure
            err_text = stderr or stdout or "<no output>"
            return {
                "success": False,
                "error": f"Subprocess failure (non-json output): {err_text}",
                "tb": err_text,
                "time_ms": (end - start) * 1000.0,
            }
    except subprocess.TimeoutExpired as te:
        # kill attempted by subprocess.run when timeout occurs
        end = time.time()
        return {
            "success": False,
            "error": f"Timeout after {timeout}s",
            "tb": f"TimeoutExpired: {te}",
            "time_ms": (end - start) * 1000.0,
        }
    except Exception as e:
        end = time.time()
        return {
            "success": False,
            "error": str(e),
            "tb": traceback.format_exc(),
            "time_ms": (end - start) * 1000.0,
        }


# ----------
# Helpers
# ----------
def safe_read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (IOError, UnicodeDecodeError):
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return None


def analyze_ast_symbols(file_path: Path) -> Dict[str, Any]:
    results = {
        "functions": set(),
        "classes": set(),
        "assigns": set(),
        "all": None,
        "error": None,
    }
    src = safe_read_text(file_path)
    if src is None:
        results["error"] = "Could not read file."
        return results
    try:
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                results["functions"].add(node.name)
            elif isinstance(node, ast.ClassDef):
                results["classes"].add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        results["assigns"].add(t.id)
                        if t.id == "__all__":
                            try:
                                values = []
                                if isinstance(node.value, (ast.List, ast.Tuple)):
                                    for elt in node.value.elts:
                                        if isinstance(elt, ast.Constant) and isinstance(
                                            elt.value, str
                                        ):
                                            values.append(elt.value)
                                        else:
                                            values = "unsupported"  # type: ignore
                                            break
                                else:
                                    values = "unsupported"
                                results["all"] = values
                            except Exception:
                                results["all"] = "unsupported"
    except SyntaxError as e:
        results["error"] = f"SyntaxError on line {e.lineno}"
    except Exception as e:
        results["error"] = str(e)
    return results


def find_module_file_path(module_name: str) -> Optional[Path]:
    # Try importlib.util.find_spec first
    try:
        spec = importlib.util.find_spec(module_name)
        if spec and getattr(spec, "origin", None):
            origin = spec.origin
            if origin and os.path.exists(origin):
                return Path(origin)
    except Exception:
        pass

    # Try importlib.resources for packages (defensive)
    try:
        try:
            res = importlib.resources.files(module_name)
            candidate = res / "__init__.py"
            with importlib.resources.as_file(candidate) as p:
                if p.exists():
                    return Path(p)
        except Exception:
            pass
    except Exception:
        pass

    # Fallback: scan sys.path
    parts = module_name.split(".")
    for sp in sys.path:
        if not sp:
            continue
        try:
            base = Path(sp)
        except Exception:
            continue
        potential_pkg = base.joinpath(*parts)
        init_py = potential_pkg / "__init__.py"
        if init_py.is_file():
            return init_py
        module_py = base.joinpath(*parts).with_suffix(".py")
        if module_py.is_file():
            return module_py
    return None


def suggest_pip_names(module_name: str) -> List[str]:
    base = module_name.split(".")[0].lower()
    candidates = [base, base.replace("_", "-")]
    if importlib_metadata:
        try:
            dists = [
                d.metadata.get("Name", "").lower()
                for d in importlib_metadata.distributions()
            ]
            similar = [d for d in dists if base in d]
            candidates.extend(similar[:3])
        except Exception:
            pass
    # unique
    seen = []
    for c in candidates:
        if c and c not in seen:
            seen.append(c)
    return seen


def is_standard_lib(module_name: str) -> bool:
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return False
        origin = getattr(spec, "origin", None)
        if origin in (None, "built-in", "frozen"):
            return True
        stdlib = sysconfig.get_paths().get("stdlib")
        if stdlib and str(origin).startswith(str(stdlib)):
            return True
        # fallback: treat as stdlib if not in site-packages path
        return "site-packages" not in str(origin)
    except Exception:
        return False


def detect_env() -> Dict[str, bool]:
    try:
        is_venv = hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        )
    except Exception:
        is_venv = False
    is_editable = any(
        "editable" in (p or "") for p in sys.path if p and "site-packages" in p
    )
    return {"virtualenv": is_venv, "editable": is_editable}


def _is_ignored_path(p: Path) -> bool:
    s = str(p).lower()
    ignored = [
        "site-packages",
        os.sep + ".venv" + os.sep,
        os.sep + "venv" + os.sep,
        os.sep + ".git" + os.sep,
        os.sep + "__pycache__" + os.sep,
        ".egg-info",
        os.sep + "build" + os.sep,
        os.sep + "dist" + os.sep,
    ]
    return any(x in s for x in ignored)


def find_symbol_definitions_in_repo(
    project_root: Path, symbol: str, max_results: int = 50
) -> List[Tuple[Path, int, str]]:
    results: List[Tuple[Path, int, str]] = []
    if not project_root.exists():
        return results
    try:
        for path in project_root.rglob("*.py"):
            if _is_ignored_path(path):
                continue
            src = safe_read_text(path)
            if not src:
                continue
            try:
                tree = ast.parse(src)
            except Exception:
                continue
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == symbol:
                    results.append((path, node.lineno, "class"))
                elif (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == symbol
                ):
                    results.append((path, node.lineno, "function"))
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == symbol:
                            results.append((path, node.lineno, "assign"))
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "__all__":
                            try:
                                if isinstance(node.value, (ast.List, ast.Tuple)):
                                    for elt in node.value.elts:
                                        if (
                                            isinstance(elt, ast.Constant)
                                            and isinstance(elt.value, str)
                                            and elt.value == symbol
                                        ):
                                            results.append(
                                                (path, node.lineno, "all_export")
                                            )
                            except Exception:
                                pass
            if len(results) >= max_results:
                break
    except Exception:
        pass
    return results


def find_import_usages_in_repo(
    project_root: Path,
    symbol: str,
    from_module: Optional[str] = None,
    max_results: int = 200,
) -> List[Tuple[Path, int, str]]:
    results: List[Tuple[Path, int, str]] = []
    if not project_root.exists():
        return results
    try:
        for path in project_root.rglob("*.py"):
            if _is_ignored_path(path):
                continue
            src = safe_read_text(path)
            if not src:
                continue
            try:
                tree = ast.parse(src)
            except Exception:
                continue
            imports_map: Dict[str, str] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if from_module and not (
                        mod == from_module or mod.startswith(from_module + ".")
                    ):
                        continue
                    for alias in node.names:
                        if alias.name == "*":
                            results.append(
                                (path, node.lineno, f"star-import from {mod}")
                            )
                        elif alias.name == symbol:
                            results.append(
                                (
                                    path,
                                    node.lineno,
                                    f"from-import {mod} import {symbol}",
                                )
                            )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        full_mod = alias.name
                        asname = alias.asname or full_mod.split(".")[0]
                        imports_map[asname] = full_mod
                if (
                    isinstance(node, ast.Attribute)
                    and getattr(node, "attr", None) == symbol
                ):
                    base = node.value
                    if isinstance(base, ast.Name):
                        base_name = base.id
                        mapped = imports_map.get(base_name)
                        if mapped:
                            results.append(
                                (
                                    path,
                                    node.lineno,
                                    f"attr-usage {mapped}.{symbol} (via {base_name})",
                                )
                            )
                        else:
                            results.append(
                                (path, node.lineno, f"attr-usage {base_name}.{symbol}")
                            )
                    elif isinstance(base, ast.Attribute):
                        parts = []
                        cur = base
                        while isinstance(cur, ast.Attribute):
                            parts.append(cur.attr)
                            cur = cur.value
                        if isinstance(cur, ast.Name):
                            parts.append(cur.id)
                        parts = list(reversed(parts))
                        dotted = ".".join(parts)
                        results.append(
                            (path, node.lineno, f"attr-usage {dotted}.{symbol}")
                        )
            if len(results) >= max_results:
                break
    except Exception:
        pass
    return results


def find_similar_modules(
    root: Path, target: str, max_results: int = 5, threshold: float = 0.6
) -> List[Tuple[str, float]]:
    similar = []
    for p in root.rglob("*"):
        if p.is_dir() and p.name:
            mod_name = ".".join(p.relative_to(root).parts)
            ratio = difflib.SequenceMatcher(None, mod_name, target).ratio()
            if ratio > threshold:
                similar.append((mod_name, ratio))
        elif p.suffix == ".py" and p.stem:
            parts = list(p.relative_to(root).parts[:-1])  # Convert to list
            mod_name = ".".join(parts + [p.stem])
            ratio = difflib.SequenceMatcher(None, mod_name, target).ratio()
            if ratio > threshold:
                similar.append((mod_name, ratio))
    return sorted(similar, key=lambda x: x[1], reverse=True)[:max_results]


def _format_evidence_item(path: Path, lineno: int, kind: str) -> str:
    try:
        rel = path.relative_to(Path.cwd())
    except Exception:
        rel = path
    return f"{rel}:{lineno}: {kind}"


# ----------
# Core ImportDiagnostic
# ----------
class ImportDiagnostic:
    def __init__(
        self,
        continue_on_error: bool = False,
        verbose: bool = False,
        quiet: bool = False,
        exclude_patterns: Optional[List[str]] = None,
        use_emojis: bool = True,
        log_file: Optional[str] = None,
        timeout: int = 0,
        dry_run: bool = False,
        unload: bool = False,
        json_output: bool = False,
        parallel: int = 0,
        max_depth: Optional[int] = None,
        dev_mode: bool = False,
        dev_trace: bool = False,
        graph: bool = False,
        dot_file: Optional[str] = None,
        allow_root: bool = False,
        show_env: bool = False,
        enable_telemetry: bool = False,
        enable_cache: bool = False,
        generate_fixes: bool = False,
        fix_output: Optional[str] = None,
        safe_mode: bool = True,
        safe_skip_imports: bool = True,
        max_scan_results: int = 200,  # New: Configurable max for scans
    ):
        if os.name != "nt" and os.geteuid() == 0 and not allow_root:
            raise PermissionError(
                "Refusing to run as root (use --allow-root to override)."
            )

        self.continue_on_error = continue_on_error
        self.verbose = verbose
        self.quiet = quiet
        self.exclude_regexes = [re.compile(p) for p in (exclude_patterns or [])]
        self.use_emojis = use_emojis
        self.log_file = log_file
        self.timeout = timeout
        self.dry_run = dry_run
        self.unload = unload
        self.json_output = json_output
        self.parallel = parallel
        self.max_depth = max_depth
        self.dev_mode = dev_mode
        self.dev_trace = dev_trace
        self.graph = graph
        self.dot_file = dot_file
        self.show_env = show_env
        self.allow_root = allow_root
        self.generate_fixes = generate_fixes
        self.fix_output = fix_output
        self.safe_mode = safe_mode
        self.safe_skip_imports = safe_skip_imports
        self.max_scan_results = max_scan_results  # New

        self._current_package: Optional[str] = None

        # Telemetry & cache
        self.telemetry = TelemetryCollector(enabled=enable_telemetry)
        self.cache = DiagnosticCache() if enable_cache else None
        self.auto_fixes: List[AutoFix] = []

        # Logging
        self.show_details = self.verbose or not self.quiet
        self.logger = self._setup_logger(
            log_file, logging.DEBUG if self.verbose else logging.INFO
        )

        # Discovery and results
        self.discovered_modules: Set[str] = set()
        self.discovery_errors: List[Tuple[str, str]] = []
        self.imported_modules: Set[str] = set()
        self.failed_modules: List[Tuple[str, str]] = []
        self.skipped_modules: Set[str] = set()
        self.timings: Dict[str, float] = {}
        self.package_tree: Dict[str, List[str]] = defaultdict(list)
        self.start_time = time.time()

        # Tracing
        self._import_stack: List[str] = []
        self._edges: Set[Tuple[str, str]] = set()
        self._original_import = None

        # Env detection
        self.env_info = detect_env()
        if self.env_info["virtualenv"]:
            self._log("Detected virtualenv - good for isolation.", level="INFO")
        else:
            self._log(
                "No virtualenv detected. Recommend using one for safety.",
                level="WARNING",
            )
            if self.safe_mode and self.safe_skip_imports and not self.dry_run:
                self._log(
                    "Safe mode active and safe-skip-imports enabled: imports will be skipped (discovery-only). Use --no-safe-mode or --no-safe-skip to override.",
                    level="WARNING",
                )
                self._skip_imports_enforced_by_safe_mode = True
            else:
                self._skip_imports_enforced_by_safe_mode = False

        if self.env_info["editable"]:
            self._log(
                "Detected editable install - watch for path issues.", level="INFO"
            )

        self.project_root: Path = Path(os.getcwd())

    def _setup_logger(self, log_file: Optional[str], level: int) -> logging.Logger:
        logger = logging.getLogger("import_diagnostic")
        logger.setLevel(level)
        # Avoid duplicate handlers
        if not getattr(logger, "_initialized_by_import_diag", False):
            formatter = logging.Formatter(
                "%(asctime)s %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
            )
            ch = logging.StreamHandler()
            ch.setLevel(level)
            ch.setFormatter(formatter)
            logger.addHandler(ch)
            if log_file:
                fh = RotatingFileHandler(
                    log_file, maxBytes=5 * 1024 * 1024, backupCount=5
                )
                fh.setLevel(min(logging.DEBUG, level))
                fh.setFormatter(formatter)
                logger.addHandler(fh)
            logger._initialized_by_import_diag = True  # type: ignore
        return logger

    def _log(self, message: str, level: str = "INFO") -> None:
        # map to logger methods
        log_func = {
            "INFO": self.logger.info,
            "SUCCESS": self.logger.info,
            "ERROR": self.logger.error,
            "DEBUG": self.logger.debug,
            "WARNING": self.logger.warning,
        }.get(level, self.logger.info)
        prefix = ""
        if self.use_emojis:
            icons = {
                "INFO": "ℹ️ ",
                "SUCCESS": "✅ ",
                "ERROR": "❌ ",
                "DEBUG": "🔍 ",
                "WARNING": "⚠️ ",
            }
            prefix = icons.get(level, "")
        log_func(f"{prefix}{message}")

    def _should_skip_module(self, module_name: str) -> bool:
        skipped = any(pat.search(module_name) for pat in self.exclude_regexes)
        if skipped:
            self.skipped_modules.add(module_name)
        return skipped

    def run_diagnostic(
        self, package_name: str, package_dir: Optional[str] = None
    ) -> bool:
        self._current_package = package_name
        self._print_header(package_name, package_dir)

        if package_dir:
            dir_path = Path(package_dir).resolve()
            parent_dir = str(dir_path.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
                self._log(f"Added to Python path: {parent_dir}", level="DEBUG")
            try:
                self.project_root = Path(package_dir).resolve()
            except Exception:
                self.project_root = Path.cwd()

        if not self._validate_package(package_name):
            return False

        # Discovery
        self._log("-" * 70, level="DEBUG")
        self._log("🔎 Starting Discovery Phase...", level="INFO")
        self._discover_all_modules(package_name)

        # If safe-mode enforced skip, treat as discovery-only run unless user explicitly requested imports
        skip_imports = (
            getattr(self, "_skip_imports_enforced_by_safe_mode", False) or self.dry_run
        )

        if skip_imports:
            self._log("Running discovery-only (imports skipped).", level="WARNING")
        else:
            self._log("\n" + "-" * 70, level="DEBUG")
            self._log("📦 Starting Import Phase...", level="INFO")
            self._import_discovered_modules()

        # Fix generation
        if self.generate_fixes and self.auto_fixes:
            self._export_fixes()

        # Output
        if self.json_output:
            self._print_json_summary(package_name, discovery_only=skip_imports)
        else:
            if self.continue_on_error or len(self.failed_modules) == 0:
                self._print_summary(package_name, discovery_only=skip_imports)
            else:
                self._log(
                    "\n❌ Diagnostic halted due to error. For a full report with all potential issues, rerun with --continue-on-error.",
                    level="ERROR",
                )
                self._print_additional_tips()

        if self.graph and self.dot_file and self._edges:
            self._export_graph()

        # Successful if no failures/discovery errors (discovery-only still "success" for discovery)
        return len(self.failed_modules) == 0 and len(self.discovery_errors) == 0

    def _print_header(self, package_name: str, package_dir: Optional[str]):
        self._log("=" * 70, level="INFO")
        title = (
            "🔍 ADVANCED IMPORT DIAGNOSTIC TOOL V20 ⚡"
            if self.use_emojis
            else "ADVANCED IMPORT DIAGNOSTIC TOOL V20"
        )
        self._log(title, level="INFO")
        self._log("=" * 70, level="INFO")
        self._log(f"Target package: {package_name}", level="INFO")
        self._log(f"Python version: {sys.version.splitlines()[0]}", level="INFO")
        self._log(f"Working directory: {os.getcwd()}", level="INFO")
        if package_dir:
            self._log(f"Package dir: {package_dir}", level="INFO")
        self._log(f"Continue on error: {self.continue_on_error}", level="INFO")
        self._log(f"Dry run: {self.dry_run}", level="INFO")
        self._log(f"Safe mode: {self.safe_mode}", level="INFO")
        self._log(
            f"Safe-skip-imports enforced: {getattr(self, '_skip_imports_enforced_by_safe_mode', False)}",
            level="INFO",
        )
        self._log(f"Telemetry: {self.telemetry.enabled}", level="INFO")
        self._log(f"Caching: {self.cache is not None}", level="INFO")
        self._log(f"Auto-fix generation: {self.generate_fixes}", level="INFO")
        if self.log_file:
            self._log(f"Logging to file: {self.log_file}", level="INFO")

    def _validate_package(self, package_name: str) -> bool:
        try:
            spec = importlib.util.find_spec(package_name)
            if spec is None:
                self._log(f"Package '{package_name}' not found.", level="ERROR")
                self._diagnose_path_issue(package_name)
                return False
            return True
        except Exception as e:
            self._log(f"Cannot locate package '{package_name}': {e}", level="ERROR")
            self._diagnose_path_issue(package_name)
            return False

    def _discover_all_modules(self, root_package: str):
        processed: Set[str] = set()
        stack: List[Tuple[str, List[str]]] = [(root_package, [])]

        try:
            root_spec = importlib.util.find_spec(root_package)
            if root_spec is None:
                self.discovery_errors.append((root_package, "Root package not found."))
                self._log(
                    f"❌ Could not find root package '{root_package}'.", level="ERROR"
                )
                return
            sub_locs = getattr(root_spec, "submodule_search_locations", None)
            stack[0] = (root_package, list(sub_locs) if sub_locs else [])
        except Exception as e:
            self.discovery_errors.append((root_package, str(e)))
            self._log(f"❌ Error locating root '{root_package}': {e}", level="ERROR")
            if not self.continue_on_error:
                self._log(
                    "Halting discovery due to error. Use --continue-on-error to find all issues.",
                    level="ERROR",
                )
                return

        while stack:
            package_name, search_locations = stack.pop()
            if package_name in processed:
                continue
            processed.add(package_name)
            if not self._should_skip_module(package_name):
                self.discovered_modules.add(package_name)
            self._log(f"Discovered: {package_name}", level="DEBUG")

            if not search_locations:
                continue

            try:
                for loc in search_locations:
                    path = Path(loc)
                    if not path.exists():
                        continue
                    for entry in path.iterdir():
                        if (
                            entry.name.startswith("_")
                            and not entry.name == "__init__.py"
                        ):
                            continue
                        if entry.is_dir() and (entry / "__init__.py").exists():
                            sub_name = f"{package_name}.{entry.name}"
                            if self._should_skip_module(sub_name):
                                continue
                            self.discovered_modules.add(sub_name)
                            self.package_tree[package_name].append(sub_name)
                            sub_spec = importlib.util.find_spec(sub_name)
                            sub_locs = (
                                list(
                                    getattr(
                                        sub_spec,
                                        "submodule_search_locations",
                                        [str(entry)],
                                    )
                                )
                                if sub_spec
                                else [str(entry)]
                            )
                            stack.append((sub_name, sub_locs))
                            self._log(f"  Found package: '{sub_name}'", level="DEBUG")
                        elif entry.suffix == ".py" and entry.name != "__init__.py":
                            sub_name = f"{package_name}.{entry.stem}"
                            if self._should_skip_module(sub_name):
                                continue
                            self.discovered_modules.add(sub_name)
                            self.package_tree[package_name].append(sub_name)
                            self._log(f"  Found module: '{sub_name}'", level="DEBUG")
            except Exception as e:
                self.discovery_errors.append((package_name, str(e)))
                self._log(
                    f"  - ⚠️ Error exploring '{package_name}': {e}", level="WARNING"
                )
                if not self.continue_on_error:
                    self._log(
                        "Halting discovery due to error. Use --continue-on-error to find all issues.",
                        level="WARNING",
                    )
                    return

    def _import_discovered_modules(self):
        sorted_modules = sorted(self.discovered_modules)

        if self.dev_trace:
            self._install_import_tracer()

        effective_parallel = self.parallel if self.parallel > 0 else 0
        if effective_parallel > 0 and self.dev_trace:
            self._log(
                "Dev trace disables parallel; running sequential.", level="WARNING"
            )
            effective_parallel = 0

        class _DummyProgress:
            def __init__(self, total: int):
                self.total = total
                self._count = 0

            def update(self, n: int = 1):
                self._count += n

            def close(self):
                pass

        progress_bar = None
        if tqdm is not None:
            progress_bar = tqdm(
                total=len(sorted_modules), desc="Importing modules", disable=self.quiet
            )
        else:
            progress_bar = _DummyProgress(len(sorted_modules))

        should_break = False

        # Use ThreadPoolExecutor to run subprocess-based workers concurrently.
        if effective_parallel > 0:
            # submit tasks to threadpool; each task spawns a subprocess (IO/CPU external work)
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=effective_parallel
            ) as executor:
                future_map = {
                    executor.submit(import_module_worker, mod, self.timeout): mod
                    for mod in sorted_modules
                }
                try:
                    for future in concurrent.futures.as_completed(future_map):
                        if should_break:
                            break
                        mod = future_map[future]
                        try:
                            result = future.result()
                            self._process_import_result(mod, result)
                        except Exception as e:
                            # Unexpected exception during worker invocation
                            self._handle_error(mod, e, tb_str=traceback.format_exc())
                            if not self.continue_on_error:
                                should_break = True
                        progress_bar.update(1)
                finally:
                    # best-effort shutdown (threads will finish quickly as subprocesses exit)
                    pass
        else:
            # sequential imports using the subprocess-backed worker (enforces timeout)
            for i, mod in enumerate(sorted_modules):
                if should_break:
                    break

                if self.cache:
                    module_path = find_module_file_path(mod)
                    cached = self.cache.get(mod, module_path)
                    if cached:
                        self._log(
                            f"[{i + 1}/{len(sorted_modules)}] Using cached result for '{mod}'",
                            level="DEBUG",
                        )
                        if cached.get("success"):
                            self.imported_modules.add(mod)
                            self.timings[mod] = cached.get("time_ms", 0) / 1000.0
                        else:
                            self.failed_modules.append(
                                (mod, cached.get("error", "<cached-error>"))
                            )
                            self.timings[mod] = cached.get("time_ms", 0) / 1000.0
                        progress_bar.update(1)
                        continue

                self._log(
                    f"[{i + 1}/{len(sorted_modules)}] Importing '{mod}' (subprocess)...",
                    level="INFO",
                )
                start = time.time()
                try:
                    result = import_module_worker(mod, self.timeout)
                    elapsed = result.get("time_ms", (time.time() - start) * 1000.0)
                    if result.get("success"):
                        self.imported_modules.add(mod)
                        self.timings[mod] = elapsed / 1000.0
                        self._log(
                            f"SUCCESS: Imported '{mod}' ({elapsed:.0f}ms)",
                            level="SUCCESS",
                        )
                        if self.cache:
                            self.cache.set(
                                mod,
                                find_module_file_path(mod),
                                {"success": True, "error": None, "time_ms": elapsed},
                            )
                        self.telemetry.record("import_success", mod, elapsed)
                        if self.unload:
                            try:
                                del sys.modules[mod]
                            except Exception:
                                pass
                    else:
                        # failure returned by subprocess worker
                        self.timings[mod] = elapsed / 1000.0
                        if self.cache:
                            self.cache.set(
                                mod,
                                find_module_file_path(mod),
                                {
                                    "success": False,
                                    "error": result.get("error", "<error>"),
                                    "time_ms": elapsed,
                                },
                            )
                        self.telemetry.record(
                            "import_failure", mod, elapsed, error=result.get("error")
                        )
                        err = Exception(result.get("error", "<error>"))
                        self._handle_error(mod, err, tb_str=result.get("tb"))
                        if not self.continue_on_error:
                            should_break = True
                except Exception as e:
                    elapsed = (time.time() - start) * 1000.0
                    if self.cache:
                        try:
                            self.cache.set(
                                mod,
                                find_module_file_path(mod),
                                {"success": False, "error": str(e), "time_ms": elapsed},
                            )
                        except Exception:
                            pass
                    self.telemetry.record("import_failure", mod, elapsed, error=str(e))
                    self._handle_error(mod, e, tb_str=traceback.format_exc())
                    if not self.continue_on_error:
                        should_break = True
                finally:
                    progress_bar.update(1)

        try:
            progress_bar.close()
        except Exception:
            pass

        if self.dev_trace:
            self._uninstall_import_tracer()

    def _process_import_result(self, mod: str, result: Dict):
        # worker returns time_ms
        if result.get("success"):
            self.imported_modules.add(mod)
            ms = result.get("time_ms", 0.0)
            self.timings[mod] = ms / 1000.0
            self._log(f"SUCCESS: Imported '{mod}' ({ms:.0f}ms)", level="SUCCESS")
            self.telemetry.record("import_success", mod, ms)
        else:
            err = Exception(result.get("error", "<unknown>"))
            tb_str = result.get("tb")
            self.timings[mod] = result.get("time_ms", 0.0) / 1000.0
            self._handle_error(mod, err, tb_str=tb_str)
            self.telemetry.record(
                "import_failure",
                mod,
                result.get("time_ms", 0.0),
                error=result.get("error"),
            )

    def _handle_error(
        self, module_name: str, error: Exception, tb_str: Optional[str] = None
    ) -> None:
        original_error = str(error)
        error_str = original_error.lower()
        self.failed_modules.append((module_name, original_error))
        error_type = type(error).__name__

        self._log("\n" + "=" * 70, level="ERROR")
        self._log(f"🚨 FAILED TO IMPORT: '{module_name}'", level="ERROR")
        self._log(f"🔥 ROOT CAUSE: {error_type}: {error}", level="ERROR")
        self._log("=" * 70, level="ERROR")

        context = self._analyze_error_context(
            module_name, error_str, original_error, tb_str
        )

        self._log(
            f"📋 Classification: {context.get('type', 'unknown').replace('_', ' ').title()}",
            level="INFO",
        )
        if context.get("evidence"):
            self._log("📊 Evidence:", level="INFO")
            for ev in context.get("evidence", []):
                self._log(f"  - {ev}", level="INFO")

        evidence_weights = {
            "ast_definition": sum(
                1
                for e in context.get("evidence", [])
                if "class" in e or "function" in e or "assign" in e
            ),
            "ast_usage": sum(
                1
                for e in context.get("evidence", [])
                if "from-import" in e or "attr-usage" in e
            ),
            "syspath_resolvable": sum(
                1
                for s in context.get("suggestions", [])
                if "Possible correct import" in s
            ),
            "exact_match": 1
            if any("exists in" in e for e in context.get("evidence", []))
            else 0,
            "fuzzy_match": len(context.get("similar_modules", [])),  # New
        }

        conf_score, conf_explanation = ConfidenceCalculator.calculate(
            evidence_weights, len(context.get("suggestions", []))
        )
        self._log(f"🧠 Confidence Score: {conf_score}/10", level="INFO")
        self._log(f"   {conf_explanation}", level="INFO")

        self._log("💡 Recommended Actions:", level="INFO")
        for i, sug in enumerate(context.get("suggestions", []), 1):
            self._log(f"  {i}. {sug}", level="INFO")

        if self.generate_fixes and context.get("auto_fix"):
            self.auto_fixes.append(context["auto_fix"])
            self._log(
                f"🔧 Auto-fix generated (confidence: {context['auto_fix'].confidence:.0%})",
                level="INFO",
            )

        if context.get("type") == "local_module":
            self._log("🛠️ Development Tips:", level="INFO")
            self._log(
                "  - Run from the correct directory containing your package",
                level="INFO",
            )
            self._log(
                "  - Use 'pip install -e .' if this is a development package",
                level="INFO",
            )

        self._diagnose_path_issue(module_name)

        self._log("\n--- START OF FULL TRACEBACK ---", level="INFO")
        self._log(tb_str or traceback.format_exc(), level="INFO")
        self._log("--- END OF FULL TRACEBACK ---", level="INFO")
        self._log("=" * 70 + "\n", level="ERROR")

    def _parse_tb_for_import(
        self, tb_str: Optional[str], original_error: str
    ) -> Optional[Dict]:
        if not tb_str:
            return None
        lines = tb_str.splitlines()
        for i in range(len(lines) - 1, -1, -1):
            if "<module>" in lines[i] and "File" in lines[i]:
                match = re.match(r'\s*File "(.+)", line (\d+), in <module>', lines[i])
                if match:
                    file_path_str = match.group(1)
                    line_num = int(match.group(2))
                    file_path = Path(file_path_str)
                    src = safe_read_text(file_path)
                    if src:
                        try:
                            tree = ast.parse(src)
                            for node in ast.walk(tree):
                                if (
                                    isinstance(node, ast.ImportFrom)
                                    and node.lineno == line_num
                                ):
                                    return {
                                        "module": node.module or "",
                                        "symbols": [a.name for a in node.names],
                                        "file_path": file_path_str,
                                        "line_num": line_num,
                                    }
                            # For multiline, find closest
                            closest = None
                            min_diff = float("inf")
                            for node in ast.walk(tree):
                                if isinstance(node, ast.ImportFrom):
                                    diff = abs(node.lineno - line_num)
                                    if diff < min_diff:
                                        min_diff = diff
                                        closest = node
                            if closest and min_diff <= 3:
                                return {
                                    "module": closest.module or "",
                                    "symbols": [a.name for a in closest.names],
                                    "file_path": file_path_str,
                                    "line_num": line_num,
                                }
                        except Exception:
                            pass
                    # Fallback parse if no AST
                    if i + 1 < len(lines):
                        code_line = lines[i + 1].strip()
                        if code_line.startswith("from "):
                            parts = code_line.split(" import ")
                            if len(parts) == 2:
                                mod = parts[0][5:].strip()
                                sym_str = parts[1].strip()
                                if sym_str.startswith("("):
                                    sym_str = sym_str[1:]
                                if sym_str.endswith(")"):
                                    sym_str = sym_str[:-1]
                                symbols = [
                                    s.strip() for s in sym_str.split(",") if s.strip()
                                ]
                                if symbols:
                                    return {
                                        "module": mod,
                                        "symbols": symbols,
                                        "file_path": file_path_str,
                                        "line_num": line_num,
                                    }
        return None

    def _path_to_module(self, path: Path) -> str:
        candidates = []
        full_p_str = str(path.resolve())
        for sp in sys.path:
            if not sp:
                continue
            try:
                sp_p = Path(sp).resolve()
                sp_str = str(sp_p)
                if full_p_str.startswith(sp_str + os.sep) or full_p_str == sp_str:
                    rel_str = full_p_str[len(sp_str) :].lstrip(os.sep)
                    rel_parts = rel_str.split(os.sep)
                    if rel_parts and rel_parts[-1] == "__init__.py":
                        parts = rel_parts[:-1]
                    elif rel_parts:
                        parts = rel_parts[:-1] + [Path(rel_parts[-1]).stem]
                    else:
                        parts = []
                    mod = ".".join(parts)
                    candidates.append((mod, len(sp_str)))
            except Exception:
                pass
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]
        return ""

    def _analyze_error_context(
        self,
        module_name: str,
        error_str: str,
        original_error: str,
        tb_str: Optional[str] = None,
    ) -> Dict:
        context: Dict[str, Any] = {
            "type": "unknown",
            "suggestions": [],
            "evidence": [],
            "auto_fix": None,
            "similar_modules": [],
        }
        module_path = find_module_file_path(module_name)
        if module_path:
            context["evidence"].append(f"Module file exists: {module_path}")
            try:
                perms = oct(module_path.stat().st_mode)[-3:]
                context["evidence"].append(f"Permissions: {perms}")
            except Exception:
                pass
        if "no module named" in error_str:
            missing_match = re.search(
                r"no module named ['\"]?([^'\"]+)['\"]?", original_error, re.IGNORECASE
            )
            if missing_match:
                missing_mod = missing_match.group(1)
                if module_path:
                    context["evidence"].insert(
                        0, "Error likely from inner import failure."
                    )
                    context["suggestions"].insert(
                        0, f"Fix import statements in {module_path}"
                    )
            else:
                missing_mod = module_name
            base_mod = ".".join(missing_mod.split(".")[:-1])
            if base_mod:
                try:
                    if importlib.util.find_spec(base_mod) is not None:
                        context["type"] = "local_submodule"
                        context["suggestions"].extend(
                            [
                                f"Create missing submodule '{missing_mod}' in package '{base_mod}'",
                                f"Expected path: {missing_mod.replace('.', '/')}.py or {missing_mod.replace('.', '/')}/__init__.py",
                                "Check for typos in import statements",
                                "Verify module exists in correct location",
                            ]
                        )
                        context["evidence"].append(
                            f"Parent module '{base_mod}' exists."
                        )
                except Exception as e:
                    context["evidence"].append(
                        f"Failed to check parent module: {type(e).__name__}: {e}"
                    )
            elif self._current_package and missing_mod.startswith(
                self._current_package + "."
            ):
                context["type"] = "local_module"
                context["suggestions"].extend(
                    [
                        f"Create missing local module: {missing_mod}",
                        f"Expected path: {missing_mod.replace(self._current_package + '.', '').replace('.', '/')}.py or {missing_mod.replace(self._current_package + '.', '').replace('.', '/')}/__init__.py",
                        "Check for typos in import statements",
                        "Verify module exists in correct location",
                    ]
                )
                context["evidence"].append(
                    f"Belongs to package '{self._current_package}'"
                )
            elif is_standard_lib(missing_mod.split(".")[0]):
                context["type"] = "standard_library"
                context["suggestions"].extend(
                    [
                        f"Check Python installation for '{missing_mod}'",
                        "Verify version compatibility",
                        "Check spelling/case",
                    ]
                )
            else:
                context["type"] = "external_dependency"
                pips = suggest_pip_names(missing_mod)
                context["suggestions"].extend([f"pip install {p}" for p in pips])
                context["suggestions"].extend(
                    [
                        "Check requirements.txt/setup.py",
                        "Verify installed in current env",
                    ]
                )
                if pips:
                    context["auto_fix"] = FixGenerator.generate_missing_dependency_fix(
                        missing_mod, pips[0]
                    )

            # Fuzzy search for similar modules to missing_mod
            similars = find_similar_modules(
                self.project_root, missing_mod, self.max_scan_results // 10
            )
            if similars:
                context["similar_modules"] = similars
                for mod, ratio in similars:
                    context["evidence"].append(
                        f"Similar module found: {mod} (similarity {ratio:.2f})"
                    )
                    context["suggestions"].append(
                        f"Possible alternative: import from {mod}"
                    )

        elif "cannot import name" in error_str:
            name_match = re.search(
                r"cannot import name ['\"]?([^'\"]+)['\"]? from ['\"]?([^'\"]+)['\"]?",
                original_error,
            )
            if name_match:
                name, from_mod = name_match.groups()
                context["type"] = "missing_name"
                context["suggestions"] = [
                    f"Check if '{name}' defined in '{from_mod}'",
                    "Verify spelling/case",
                    "Check circular dependencies",
                    "Examine __all__ if present",
                ]
                source_path = find_module_file_path(from_mod)
                if source_path:
                    symbols = analyze_ast_symbols(source_path)
                    if symbols.get("error"):
                        context["evidence"].append(f"AST error: {symbols['error']}")
                    else:
                        if (
                            name in symbols.get("functions", set())
                            or name in symbols.get("classes", set())
                            or name in symbols.get("assigns", set())
                        ):
                            context["evidence"].append(
                                f"'{name}' exists in {source_path}! Likely circular import."
                            )
                            if self._import_stack:
                                context["auto_fix"] = (
                                    FixGenerator.generate_circular_import_fix(
                                        self._import_stack + [module_name]
                                    )
                                )
                        else:
                            context["evidence"].append(
                                f"'{name}' not found in AST of {source_path}."
                            )
                        if symbols.get("all"):
                            context["evidence"].append(f"__all__: {symbols['all']}")

                try:
                    repo_root = (
                        self.project_root
                        if hasattr(self, "project_root") and self.project_root
                        else Path.cwd()
                    )
                    defs = find_symbol_definitions_in_repo(
                        repo_root, name, self.max_scan_results // 4
                    )  # Adjustable

                    usages = find_import_usages_in_repo(
                        repo_root,
                        name,
                        from_module=from_mod,
                        max_results=self.max_scan_results,
                    )

                    correct_module = None
                    if defs:
                        for p, ln, kind in defs:
                            context["evidence"].append(
                                _format_evidence_item(p, ln, kind)
                            )
                            try:
                                full_p = p.resolve()
                                for sp in sys.path:
                                    try:
                                        sp_p = Path(sp).resolve()
                                    except Exception:
                                        continue
                                    try:
                                        rel = full_p.relative_to(sp_p)
                                        # build module path
                                        if rel.name == "__init__.py":
                                            parts = list(rel.parts[:-1])
                                        else:
                                            parts = list(rel.parts[:-1]) + [rel.stem]
                                        mod = ".".join(parts)
                                        suggestion = f"Possible correct import: from {mod} import {name}"
                                        if suggestion not in context["suggestions"]:
                                            context["suggestions"].append(suggestion)
                                        if not correct_module:
                                            correct_module = mod
                                        break
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    else:
                        context["evidence"].append(
                            f"No definition of '{name}' found in repo (AST scan)."
                        )

                    if usages:
                        for p, ln, kind in usages:
                            context["evidence"].append(
                                _format_evidence_item(p, ln, kind)
                            )

                    if correct_module and correct_module != from_mod:
                        context["auto_fix"] = FixGenerator.generate_missing_import_fix(
                            from_mod, name, correct_module
                        )

                except Exception as e:
                    context["evidence"].append(
                        f"Repo scan failed: {e} (tool continued safely)"
                    )
        elif "circular import" in error_str:
            context["type"] = "circular_import"
            context["suggestions"] = [
                "Refactor to break cycle",
                "Use lazy imports",
                "Restructure modules",
            ]
            if self._import_stack:
                context["evidence"].append(f"Chain: {' -> '.join(self._import_stack)}")
                context["auto_fix"] = FixGenerator.generate_circular_import_fix(
                    self._import_stack + [module_name]
                )
        elif any(
            k in error_str for k in ["dll load failed", "shared object", ".so", ".dll"]
        ):
            context["type"] = "shared_library"
            context["suggestions"] = [
                "Install system libraries",
                "Set LD_LIBRARY_PATH/PATH",
                "Check architecture (32/64-bit)",
            ]
        elif "syntaxerror" in error_str:
            context["type"] = "syntax_error"
            context["suggestions"] = [
                "Fix syntax in file",
                "Check Python version compatibility",
            ]

        # New: Check for incomplete import in traceback
        if tb_str and re.search(r"import\s*\($", tb_str):
            context["type"] = (
                "incomplete_import" if context["type"] == "unknown" else context["type"]
            )
            context["evidence"].append(
                "Incomplete import statement detected (missing closing parenthesis or symbols)"
            )
            context["suggestions"].append(
                "Complete the import statement with ) and the required symbols"
            )

        return context

    def _diagnose_path_issue(self, module_name: str) -> None:
        self._log("📁 Filesystem Analysis:", level="INFO")
        file_path = find_module_file_path(module_name)
        if file_path:
            self._log(f"Found file: {file_path}", level="INFO")
            try:
                self._log(
                    f"Permissions: {oct(file_path.stat().st_mode)[-3:]}", level="INFO"
                )
            except Exception:
                pass
        else:
            self._log("No file found matching module.", level="INFO")
        self._log("Current sys.path:", level="INFO")
        for sp in sys.path:
            self._log(f"  - {sp}", level="INFO")

    def _install_import_tracer(self):
        if self._original_import is not None:
            return
        self._original_import = builtins.__import__

        def tracing_import(name, globals=None, locals=None, fromlist=(), level=0):
            parent = self._import_stack[-1] if self._import_stack else "<root>"
            self._edges.add((parent, name))
            self._import_stack.append(name)
            try:
                return self._original_import(name, globals, locals, fromlist, level)
            except Exception:
                self._log(
                    f"FAILURE CHAIN: {' -> '.join(self._import_stack)}", level="ERROR"
                )
                raise
            finally:
                self._import_stack.pop()

        builtins.__import__ = tracing_import
        self._log("Tracer installed.", level="DEBUG")

    def _uninstall_import_tracer(self):
        if self._original_import is not None:
            builtins.__import__ = self._original_import
            self._original_import = None
            self._log("Tracer removed.", level="DEBUG")

    def _export_graph(self):
        try:
            dot_path = Path(self.dot_file)
            # ensure parent exists
            dot_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                delete=False,
                dir=str(dot_path.parent or Path.cwd()),
                encoding="utf-8",
            ) as tf:
                tf.write("digraph imports {\n")
                tf.write("  node [shape=box, style=filled, fillcolor=lightblue];\n")
                failed_names = {m for m, _ in self.failed_modules}
                for a, b in sorted(self._edges):
                    color = "red" if b in failed_names else "green"
                    tf.write(f'  "{a}" -> "{b}" [color={color}, penwidth=2];\n')
                tf.write("}\n")
                tmp = tf.name
            os.replace(tmp, str(dot_path))
            self._log(
                f"Interactive graph written to {dot_path} - open in Graphviz.",
                level="INFO",
            )
        except Exception as e:
            self._log(f"Failed to write graph: {e}", level="WARNING")

    def _export_fixes(self):
        if not self.auto_fixes:
            return
        output_file = self.fix_output or "import_diagnostic_fixes.json"
        fixes_data = [asdict(fix) for fix in self.auto_fixes]
        if not validate_json(fixes_data, FIXES_SCHEMA):
            self._log(
                "Fixes JSON failed schema validation. Exporting anyway for review.",
                level="WARNING",
            )
        try:
            parent = Path(output_file).parent or Path.cwd()
            parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=str(parent), encoding="utf-8"
            ) as tf:
                json.dump(fixes_data, tf, indent=2)
                tmp = tf.name
            os.replace(tmp, output_file)
            self._log(
                f"\n🔧 Generated {len(self.auto_fixes)} automated fixes → {output_file}",
                level="INFO",
            )
            self._log("\nAuto-Fix Summary:", level="INFO")
            for fix in self.auto_fixes:
                self._log(
                    f"  • {fix.issue_type}: {fix.description} (confidence: {fix.confidence:.0%})",
                    level="INFO",
                )
        except Exception as e:
            self._log(f"Failed to export fixes: {e}", level="WARNING")

    def _print_summary(self, package_name: str, discovery_only: bool = False) -> None:
        elapsed = time.time() - self.start_time
        self._log("\n" + "=" * 70, level="INFO")
        self._log("📊 DIAGNOSTIC SUMMARY", level="INFO")
        self._log("=" * 70, level="INFO")
        total_attempted = len(self.imported_modules) + len(self.failed_modules)
        self._log(
            f"Total modules attempted (imports run): {total_attempted}", level="INFO"
        )
        self._log(f"Successful imports: {len(self.imported_modules)}", level="INFO")
        self._log(f"Failed imports: {len(self.failed_modules)}", level="INFO")
        self._log(f"Skipped modules: {len(self.skipped_modules)}", level="INFO")
        self._log(f"Time elapsed: {elapsed:.2f} seconds", level="INFO")
        if discovery_only:
            self._log(
                "Note: this was a discovery-only run (no imports performed).",
                level="WARNING",
            )
        if self.auto_fixes:
            self._log(f"Auto-fixes generated: {len(self.auto_fixes)}", level="INFO")

        if self.telemetry.enabled:
            self._log("\n📈 Telemetry Summary:", level="INFO")
            summary = self.telemetry.get_summary()
            self._log(f"  Total events: {summary['total_events']}", level="INFO")
            self._log(
                f"  Avg import time: {summary['avg_import_time_ms']:.2f}ms",
                level="INFO",
            )
            if summary["slowest_imports"]:
                self._log("  Slowest imports:", level="INFO")
                for item in summary["slowest_imports"]:
                    self._log(
                        f"    - {item['module']}: {item['duration_ms']:.2f}ms",
                        level="INFO",
                    )

        if self.show_details and self.timings:
            self._log("\nModule Timings (top 10):", level="INFO")
            for mod, t in sorted(
                self.timings.items(), key=lambda x: x[1], reverse=True
            )[:10]:
                self._log(f"  {mod}: {t:.2f}s", level="INFO")

        if self.failed_modules:
            self._log("\n❌ FAILED MODULES:", level="ERROR")
            for module, error in self.failed_modules:
                self._log(f"  • {module}: {error}", level="ERROR")

        if not self.failed_modules and not self.discovery_errors:
            self._log("\n🎉 ALL MODULES IMPORTED SUCCESSFULLY!", level="INFO")
            self._log("✨ Production-ready: No import issues detected", level="INFO")
        else:
            self._log(
                "\n❌ Issues found. Review detailed diagnostics above.", level="WARNING"
            )

        self._log("=" * 70, level="INFO")
        self._print_additional_tips()

    def _print_additional_tips(self) -> None:
        self._log("\n💡 Production Best Practices:", level="INFO")
        self._log(
            " - Integrate into CI/CD: python -m importdoc PACKAGE --json --continue-on-error",
            level="INFO",
        )
        self._log(
            " - Enable telemetry in production for monitoring: --enable-telemetry",
            level="INFO",
        )
        self._log(" - Use caching for faster builds: --enable-cache", level="INFO")
        self._log(
            " - Generate automated fixes: --generate-fixes --fix-output fixes.json",
            level="INFO",
        )
        self._log(
            " - Always run in a virtualenv for peace of mind; use --no-safe-mode if you intentionally want imports.",
            level="INFO",
        )

    def _print_json_summary(
        self, package_name: str, discovery_only: bool = False
    ) -> None:
        elapsed = time.time() - self.start_time
        summary = {
            "version": __version__,
            "package": package_name,
            "discovered_modules": list(self.discovered_modules),
            "discovery_errors": [
                {"module": m, "error": e} for m, e in self.discovery_errors
            ],
            "imported_modules": list(self.imported_modules),
            "failed_modules": [
                {"module": m, "error": e} for m, e in self.failed_modules
            ],
            "skipped_modules": list(self.skipped_modules),
            "timings": self.timings,
            "module_tree": dict(self.package_tree),
            "env_info": self.env_info,
            "elapsed_seconds": elapsed,
            "auto_fixes": [asdict(fix) for fix in self.auto_fixes],
            "telemetry": self.telemetry.get_summary()
            if self.telemetry.enabled
            else None,
            "health_check": {
                "passed": len(self.failed_modules) == 0,
                "total_modules": len(self.discovered_modules),
                "success_rate": len(self.imported_modules)
                / max(1, len(self.discovered_modules))
                if self.discovered_modules
                else 0.0,
                "safety_note": "Run in venv for best practices"
                if not self.env_info["virtualenv"]
                else "Venv detected - good!",
                "discovery_only": discovery_only,
            },
        }
        if not validate_json(summary, JSON_SUMMARY_SCHEMA):
            self._log(
                "Summary JSON failed schema validation. Outputting anyway.",
                level="WARNING",
            )
        sys.stdout.write(json.dumps(summary, indent=2))


# ----------
# CLI entrypoint
# ----------
def main():
    parser = argparse.ArgumentParser(
        description="Advanced Import Diagnostic Tool V20 - Hardened production build with enhanced diagnosis",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("package", help="Root package to diagnose.")
    parser.add_argument("--dir", help="Package directory (adds parent to sys.path).")
    parser.add_argument(
        "--continue-on-error", action="store_true", help="Continue after errors."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Discover only, no imports."
    )
    parser.add_argument("--max-depth", type=int, help="Max discovery depth.")
    parser.add_argument("--log-file", help="Log file path.")
    parser.add_argument("--verbose", action="store_true", help="Detailed output.")
    parser.add_argument("--quiet", action="store_true", help="Minimal output.")
    parser.add_argument("--no-emoji", action="store_true", help="No emojis.")
    parser.add_argument("--timeout", type=int, default=0, help="Import timeout (s).")
    parser.add_argument("--unload", action="store_true", help="Unload after import.")
    parser.add_argument("--json", action="store_true", help="JSON output.")
    parser.add_argument("--parallel", type=int, default=0, help="Parallel imports.")
    parser.add_argument("--dev-trace", action="store_true", help="Trace import chains.")
    parser.add_argument("--graph", action="store_true", help="Generate DOT graph.")
    parser.add_argument("--dot-file", help="DOT file path.")
    parser.add_argument("--allow-root", action="store_true", help="Allow root run.")
    parser.add_argument("--show-env", action="store_true", help="Show env vars.")
    parser.add_argument(
        "--enable-telemetry", action="store_true", help="Enable production telemetry."
    )
    parser.add_argument(
        "--enable-cache", action="store_true", help="Enable result caching."
    )
    parser.add_argument(
        "--generate-fixes", action="store_true", help="Generate automated fixes."
    )
    parser.add_argument("--fix-output", help="Output file for automated fixes (JSON).")
    parser.add_argument(
        "--no-safe-mode",
        action="store_false",
        dest="safe_mode",
        help="Disable safe mode (allow imports outside venv).",
    )
    parser.add_argument(
        "--no-safe-skip",
        action="store_false",
        dest="safe_skip_imports",
        help="Do not auto-skip imports if not in venv when safe mode active.",
    )
    parser.add_argument(
        "--max-scan-results",
        type=int,
        default=200,
        help="Max results for repo scans (defs/usages/fuzzy).",
    )
    parser.add_argument("--version", action="version", version=__version__)

    args = parser.parse_args()

    diagnostic = ImportDiagnostic(
        continue_on_error=args.continue_on_error,
        verbose=args.verbose,
        quiet=args.quiet,
        use_emojis=not args.no_emoji,
        log_file=args.log_file,
        timeout=args.timeout,
        dry_run=args.dry_run,
        unload=args.unload,
        json_output=args.json,
        parallel=args.parallel,
        max_depth=args.max_depth,
        dev_trace=args.dev_trace,
        graph=args.graph,
        dot_file=args.dot_file,
        allow_root=args.allow_root,
        show_env=args.show_env,
        enable_telemetry=args.enable_telemetry,
        enable_cache=args.enable_cache,
        generate_fixes=args.generate_fixes,
        fix_output=args.fix_output,
        safe_mode=args.safe_mode,
        safe_skip_imports=args.safe_skip_imports,
        max_scan_results=args.max_scan_results,  # New
    )

    if args.dir:
        try:
            diagnostic.project_root = Path(args.dir).resolve()
        except Exception:
            diagnostic.project_root = Path.cwd()

    try:
        success = diagnostic.run_diagnostic(args.package, args.dir)
        sys.exit(0 if success else 1)
    except Exception as e:
        # if logger not available, fallback to print
        try:
            diagnostic._log(f"Internal error: {e}", level="ERROR")
            diagnostic._log(traceback.format_exc(), level="DEBUG")
        except Exception:
            print(f"Internal error: {e}", file=sys.stderr)
            traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
