# src/importdoc/modules/diagnostics.py

import builtins
import concurrent.futures
import importlib.util
import json
import logging
import os
import re
import sys
import tempfile
import time
import traceback
from collections import defaultdict
from dataclasses import asdict
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from importlib import metadata

try:
    from tqdm import tqdm
except Exception:
    tqdm = None

from .autofix import AutoFix, FixGenerator
from .cache import DiagnosticCache
from .confidence import ConfidenceCalculator
from .schemas import FIXES_SCHEMA, JSON_SUMMARY_SCHEMA, validate_json
from .telemetry import TelemetryCollector
from .utils import (
    analyze_ast_symbols,
    detect_env,
    find_import_usages_in_repo,
    find_module_file_path,
    find_similar_modules,
    find_symbol_definitions_in_repo,
    is_standard_lib,
    safe_read_text,
    suggest_pip_names,
)
from .worker import import_module_worker

__version__ = "1.0.0"
try:
    _package_version = metadata.version("importdoc")
except metadata.PackageNotFoundError:
    _package_version = "0.0.0"


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

            is_submodule_of_existing_parent = False
            if base_mod:
                try:
                    if importlib.util.find_spec(base_mod) is not None:
                        is_submodule_of_existing_parent = True
                except Exception as e:
                    context["evidence"].append(
                        f"Failed to check parent module: {type(e).__name__}: {e}"
                    )

            if is_submodule_of_existing_parent:
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
            "version": _package_version,
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
