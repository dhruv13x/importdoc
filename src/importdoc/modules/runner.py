# src/importdoc/modules/runner.py

import builtins
import concurrent.futures
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
from .processor import ResultProcessor
from .plugin import PluginManager, PluginContext


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
        self.plugin_manager = PluginManager(reporter=reporter)

        self.processor = ResultProcessor(
            config, reporter, analyzer, telemetry, cache
        )

        self.edges: Set[Tuple[str, str]] = set()
        self._import_stack: List[str] = []
        self._original_import = None
        self.project_root = Path.cwd()
        self.current_package: Optional[str] = None

    # Forward properties to processor for compatibility
    @property
    def imported_modules(self) -> Set[str]:
        return self.processor.imported_modules

    @property
    def failed_modules(self) -> List[Tuple[str, str]]:
        return self.processor.failed_modules

    @property
    def timings(self) -> Dict[str, float]:
        return self.processor.timings

    @property
    def auto_fixes(self) -> List[Any]:
        return self.processor.auto_fixes

    def run_imports(
        self,
        discovered_modules: Set[str],
        project_root: Path,
        current_package: Optional[str],
    ) -> bool:
        self.project_root = project_root
        self.current_package = current_package

        self.processor.set_context(project_root, current_package, self._import_stack)

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
                            self.processor.process_result(mod, result)
                        except Exception as e:
                            self.processor.handle_error(mod, e, tb_str=traceback.format_exc())
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
                        self.processor.process_result(mod, cached)
                        progress_bar.update(1)
                        continue

                self.reporter.log(
                    f"[{i + 1}/{len(sorted_modules)}] Importing '{mod}' (subprocess)...",
                    level="INFO",
                )
                start = time.time()
                try:
                    result = import_module_worker(mod, self.config.timeout)
                    self.processor.process_result(mod, result)

                    if not result.get("success") and not self.config.continue_on_error:
                        should_break = True

                except Exception as e:
                    self.processor.handle_error(mod, e, tb_str=traceback.format_exc())
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

        # Load plugins if configured
        if self.config.plugins:
            self.plugin_manager.load_from_config(self.config.plugins)

        # Always check if plugins are present (either loaded or manually registered)
        if self.plugin_manager.plugins:
            plugin_context = PluginContext()
            plugin_context.data["discovered_modules"] = discovered_modules
            plugin_context.data["project_root"] = project_root
            plugin_context.data["imported_modules"] = self.imported_modules
            plugin_context.data["failed_modules"] = self.failed_modules
            plugin_context.data["import_edges"] = self.edges
            # Also pass the processor for more advanced access if needed
            plugin_context.data["processor"] = self.processor

            self.plugin_manager.run_checks(plugin_context)

            if plugin_context.errors:
                for error in plugin_context.errors:
                    self.reporter.log(f"PLUGIN ERROR: [{error.type}] {error.message}", level="ERROR")
                # If plugins report errors, we should consider this a failure
                if not self.config.continue_on_error:
                    return False
            
        return len(self.processor.failed_modules) == 0

    def _process_import_result(self, mod: str, result: Dict):
        # Deprecated: usage delegated to processor
        self.processor.process_result(mod, result)

    def _handle_error(
        self,
        module_name: str,
        error: Exception,
        tb_str: Optional[str] = None,
    ) -> None:
        # Deprecated: usage delegated to processor
        self.processor.handle_error(module_name, error, tb_str)

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
