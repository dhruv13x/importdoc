# src/importdoc/modules/diagnostics.py

import time
import sys
from pathlib import Path
from typing import Optional, List

from .analysis import ErrorAnalyzer
from .cache import DiagnosticCache
from .config import DiagnosticConfig
from .discovery import ModuleDiscoverer
from .reporting import DiagnosticReporter
from .runner import ImportRunner
from .telemetry import TelemetryCollector
from .utils import detect_env

__version__ = "1.0.0"


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
        max_scan_results: int = 200,
        html: bool = False,
    ):
        self.config = DiagnosticConfig(
            continue_on_error=continue_on_error,
            verbose=verbose,
            quiet=quiet,
            exclude_patterns=exclude_patterns,
            use_emojis=use_emojis,
            log_file=log_file,
            timeout=timeout,
            dry_run=dry_run,
            unload=unload,
            json_output=json_output,
            parallel=parallel,
            max_depth=max_depth,
            dev_mode=dev_mode,
            dev_trace=dev_trace,
            graph=graph,
            dot_file=dot_file,
            allow_root=allow_root,
            show_env=show_env,
            enable_telemetry=enable_telemetry,
            enable_cache=enable_cache,
            generate_fixes=generate_fixes,
            fix_output=fix_output,
            safe_mode=safe_mode,
            safe_skip_imports=safe_skip_imports,
            max_scan_results=max_scan_results,
            html=html,
        )

        self.reporter = DiagnosticReporter(self.config)
        self.telemetry = TelemetryCollector(enabled=self.config.enable_telemetry)
        self.cache = DiagnosticCache() if self.config.enable_cache else None
        self.analyzer = ErrorAnalyzer(self.config)
        self.discoverer = ModuleDiscoverer(self.config, self.reporter)
        self.runner = ImportRunner(
            self.config, self.reporter, self.analyzer, self.telemetry, self.cache
        )

        self.env_info = detect_env()
        self._check_environment()
        
        self.start_time = time.time()

    def _check_environment(self):
        if self.env_info["virtualenv"]:
            self.reporter.log("Detected virtualenv - good for isolation.", level="INFO")
        else:
            self.reporter.log(
                "No virtualenv detected. Recommend using one for safety.",
                level="WARNING",
            )
            if self.config.safe_mode and self.config.safe_skip_imports and not self.config.dry_run:
                self.reporter.log(
                    "Safe mode active and safe-skip-imports enabled: imports will be skipped (discovery-only). Use --no-safe-mode or --no-safe-skip to override.",
                    level="WARNING",
                )
                self._skip_imports_enforced_by_safe_mode = True
            else:
                self._skip_imports_enforced_by_safe_mode = False

        if self.env_info["editable"]:
            self.reporter.log(
                "Detected editable install - watch for path issues.", level="INFO"
            )

    def run_diagnostic(
        self,
        package_name: str,
        package_dir: Optional[str] = None,
    ) -> bool:
        self.reporter.print_header(package_name, package_dir)
        self.start_time = time.time()

        # Setup paths
        if package_dir:
            dir_path = Path(package_dir).resolve()
            parent_dir = str(dir_path.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
                self.reporter.log(f"Added to Python path: {parent_dir}", level="DEBUG")
            try:
                project_root = Path(package_dir).resolve()
            except Exception:
                project_root = Path.cwd()
        else:
            project_root = Path.cwd()

        if not self.discoverer.validate_package(package_name):
            return False

        # Discovery
        self.reporter.log("-" * 70, level="DEBUG")
        self.reporter.log("🔎 Starting Discovery Phase...", level="INFO")
        
        discovery_result = self.discoverer.discover(package_name)
        
        # Check if we should skip imports
        skip_imports = (
            getattr(self, "_skip_imports_enforced_by_safe_mode", False) or self.config.dry_run
        )

        # Import Phase
        if skip_imports:
            self.reporter.log("Running discovery-only (imports skipped).", level="WARNING")
        else:
            self.reporter.log("\n" + "-" * 70, level="DEBUG")
            self.reporter.log("📦 Starting Import Phase...", level="INFO")
            self.runner.run_imports(discovery_result.discovered_modules, project_root, package_name)

        # Fix Generation
        if self.config.generate_fixes:
            self.reporter.export_fixes(self.runner.auto_fixes)

        # Output
        elapsed = time.time() - self.start_time
        if self.config.json_output:
            self.reporter.print_json_summary(
                package_name=package_name,
                discovered_modules=discovery_result.discovered_modules,
                discovery_errors=discovery_result.discovery_errors,
                imported_modules=self.runner.imported_modules,
                failed_modules=self.runner.failed_modules,
                skipped_modules=discovery_result.skipped_modules,
                timings=self.runner.timings,
                package_tree=discovery_result.package_tree,
                env_info=self.env_info,
                auto_fixes=self.runner.auto_fixes,
                telemetry_summary=self.telemetry.get_summary() if self.telemetry.enabled else None,
                elapsed_seconds=elapsed,
                discovery_only=skip_imports
            )
        else:
            if self.config.continue_on_error or len(self.runner.failed_modules) == 0:
                self.reporter.print_summary(
                    imported_modules=self.runner.imported_modules,
                    failed_modules=self.runner.failed_modules,
                    skipped_modules=discovery_result.skipped_modules,
                    timings=self.runner.timings,
                    telemetry_summary=self.telemetry.get_summary() if self.telemetry.enabled else None,
                    auto_fixes=self.runner.auto_fixes,
                    discovery_errors=discovery_result.discovery_errors,
                    elapsed_seconds=elapsed,
                    discovery_only=skip_imports
                )
            else:
                self.reporter.log(
                    "\n❌ Diagnostic halted due to error. For a full report with all potential issues, rerun with --continue-on-error.",
                    level="ERROR",
                )
                self.reporter.print_additional_tips()

        if self.config.graph and self.config.dot_file and self.runner.edges:
            failed_names = {m for m, _ in self.runner.failed_modules}
            self.reporter.export_graph(self.runner.edges, failed_names)

        if self.config.html:
            failed_names = {m for m, _ in self.runner.failed_modules}
            self.reporter.export_html(
                self.runner.edges,
                failed_names,
                package_name,
                self.runner.imported_modules,
                discovery_result.skipped_modules,
                len(discovery_result.discovery_errors) > 0 or len(self.runner.failed_modules) > 0
            )

        return len(self.runner.failed_modules) == 0 and len(discovery_result.discovery_errors) == 0
