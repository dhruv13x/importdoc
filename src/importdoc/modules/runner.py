import builtins
import concurrent.futures
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from .analysis import ErrorAnalyzer
from .cache import DiagnosticCache
from .config import DiagnosticConfig
from .reporting import DiagnosticReporter
from .telemetry import TelemetryCollector
from .utils import find_module_file_path
from .worker import import_module_worker


class ImportRunner:
    def __init__(
        self,
        config: DiagnosticConfig,
        reporter: DiagnosticReporter,
        analyzer: ErrorAnalyzer,
        telemetry: TelemetryCollector,
        cache: Optional[DiagnosticCache],
    ):
        self.config = config
        self.reporter = reporter
        self.analyzer = analyzer
        self.telemetry = telemetry
        self.cache = cache

        self.imported_modules: Set[str] = set()
        self.failed_modules: List[Tuple[str, str]] = []
        self.timings: Dict[str, float] = {}
        self.auto_fixes: List[Any] = []  # List[AutoFix]
        self.edges: Set[Tuple[str, str]] = set()

        self._import_stack: List[str] = []
        self._original_import = None
        self.project_root = Path.cwd()
        self.current_package: Optional[str] = None

    def run_imports(
        self,
        discovered_modules: Set[str],
        project_root: Path,
        current_package: Optional[str],
    ) -> bool:
        self.project_root = project_root
        self.current_package = current_package
        sorted_modules = sorted(discovered_modules)

        if self.config.dev_trace:
            self._install_import_tracer()

        effective_parallel = self.config.parallel if self.config.parallel > 0 else 0
        if effective_parallel > 0 and self.config.dev_trace:
            self.reporter.log(
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
                total=len(sorted_modules), desc="Importing modules", disable=self.config.quiet
            )
        else:
            progress_bar = _DummyProgress(len(sorted_modules))

        should_break = False

        # Use ThreadPoolExecutor to run subprocess-based workers concurrently.
        if effective_parallel > 0:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=effective_parallel
            ) as executor:
                future_map = {
                    executor.submit(import_module_worker, mod, self.config.timeout): mod
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
                            self._handle_error(mod, e, tb_str=traceback.format_exc())
                            if not self.config.continue_on_error:
                                should_break = True
                        progress_bar.update(1)
                finally:
                    pass
        else:
            for i, mod in enumerate(sorted_modules):
                if should_break:
                    break

                if self.cache:
                    module_path = find_module_file_path(mod)
                    cached = self.cache.get(mod, module_path)
                    if cached:
                        self.reporter.log(
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

                self.reporter.log(
                    f"[{i + 1}/{len(sorted_modules)}] Importing '{mod}' (subprocess)...",
                    level="INFO",
                )
                start = time.time()
                try:
                    result = import_module_worker(mod, self.config.timeout)
                    elapsed = result.get("time_ms", (time.time() - start) * 1000.0)
                    if result.get("success"):
                        self.imported_modules.add(mod)
                        self.timings[mod] = elapsed / 1000.0
                        self.reporter.log(
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
                        if self.config.unload:
                            try:
                                del sys.modules[mod]
                            except Exception:
                                pass
                    else:
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
                        if not self.config.continue_on_error:
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
                    if not self.config.continue_on_error:
                        should_break = True
                finally:
                    progress_bar.update(1)

        try:
            progress_bar.close()
        except Exception:
            pass

        if self.config.dev_trace:
            self._uninstall_import_tracer()
            
        return len(self.failed_modules) == 0

    def _process_import_result(self, mod: str, result: Dict):
        if result.get("success"):
            self.imported_modules.add(mod)
            ms = result.get("time_ms", 0.0)
            self.timings[mod] = ms / 1000.0
            self.reporter.log(f"SUCCESS: Imported '{mod}' ({ms:.0f}ms)", level="SUCCESS")
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
        self,
        module_name: str,
        error: Exception,
        tb_str: Optional[str] = None,
    ) -> None:
        original_error = str(error)
        self.failed_modules.append((module_name, original_error))
        error_type = type(error).__name__

        self.reporter.log("\n" + "=" * 70, level="ERROR")
        self.reporter.log(f"🚨 FAILED TO IMPORT: '{module_name}'", level="ERROR")
        self.reporter.log(f"🔥 ROOT CAUSE: {error_type}: {error}", level="ERROR")
        self.reporter.log("=" * 70, level="ERROR")

        context = self.analyzer.analyze(
            module_name,
            error,
            tb_str,
            self.project_root,
            self.current_package,
            self._import_stack,
        )

        self.reporter.log(
            f"📋 Classification: {context.get('type', 'unknown').replace('_', ' ').title()}",
            level="INFO",
        )
        if context.get("evidence"):
            self.reporter.log("📊 Evidence:", level="INFO")
            for ev in context.get("evidence", []):
                self.reporter.log(f"  - {ev}", level="INFO")

        conf_score, conf_explanation = self.analyzer.calculate_confidence(context)
        self.reporter.log(f"🧠 Confidence Score: {conf_score}/10", level="INFO")
        self.reporter.log(f"   {conf_explanation}", level="INFO")

        self.reporter.log("💡 Recommended Actions:", level="INFO")
        for i, sug in enumerate(context.get("suggestions", []), 1):
            self.reporter.log(f"  {i}. {sug}", level="INFO")

        if self.config.generate_fixes and context.get("auto_fix"):
            self.auto_fixes.append(context["auto_fix"])
            self.reporter.log(
                f"🔧 Auto-fix generated (confidence: {context['auto_fix'].confidence:.0%})",
                level="INFO",
            )

        if context.get("type") == "local_module":
            self.reporter.log("🛠️ Development Tips:", level="INFO")
            self.reporter.log(
                "  - Run from the correct directory containing your package",
                level="INFO",
            )
            self.reporter.log(
                "  - Use 'pip install -e .' if this is a development package",
                level="INFO",
            )

        # self.reporter.diagnose_path_issue(module_name) # Moved to discovery, let's call it from reporter if we move it back or just access utility.
        # Actually, diagnose_path_issue prints to log. I put it in discovery module but it's used here.
        # I'll duplicate/move diagnose_path_issue to Reporting or create a helper.
        # It uses find_module_file_path. I'll just reimplement a simple version here or call the one in discovery if I can access it.
        # Better: Move `diagnose_path_issue` to `DiagnosticReporter` in a follow up or just invoke it from `ModuleDiscoverer` instance if I had one.
        # But `Runner` doesn't have `ModuleDiscoverer`.
        # I'll move `diagnose_path_issue` to `DiagnosticReporter`.

        self.reporter.log("\n--- START OF FULL TRACEBACK ---", level="INFO")
        self.reporter.log(tb_str or traceback.format_exc(), level="INFO")
        self.reporter.log("--- END OF FULL TRACEBACK ---", level="INFO")
        self.reporter.log("=" * 70 + "\n", level="ERROR")

    def _install_import_tracer(self):
        if self._original_import is not None:
            return
        self._original_import = builtins.__import__

        def tracing_import(name, globals=None, locals=None, fromlist=(), level=0):
            parent = self._import_stack[-1] if self._import_stack else "<root>"
            self.edges.add((parent, name))
            self._import_stack.append(name)
            try:
                return self._original_import(name, globals, locals, fromlist, level)
            except Exception:
                self.reporter.log(
                    f"FAILURE CHAIN: {" -> ".join(self._import_stack)}", level="ERROR"
                )
                raise
            finally:
                self._import_stack.pop()

        builtins.__import__ = tracing_import
        self.reporter.log("Tracer installed.", level="DEBUG")

    def _uninstall_import_tracer(self):
        if self._original_import is not None:
            builtins.__import__ = self._original_import
            self._original_import = None
            self.reporter.log("Tracer removed.", level="DEBUG")
