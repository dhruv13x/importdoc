# src/importdoc/modules/reporting.py

import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict
from importlib import metadata
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .autofix import AutoFix
from .config import DiagnosticConfig
from .schemas import FIXES_SCHEMA, JSON_SUMMARY_SCHEMA, validate_json

try:
    _package_version = metadata.version("importdoc")
except metadata.PackageNotFoundError:
    _package_version = "0.0.0"


class DiagnosticReporter:
    def __init__(self, config: DiagnosticConfig):
        self.config = config
        self.logger = self._setup_logger(
            config.log_file, logging.DEBUG if config.verbose else logging.INFO
        )

    def _setup_logger(self, log_file: Optional[str], level: int) -> logging.Logger:
        logger = logging.getLogger("import_diagnostic")
        logger.setLevel(level)
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

    def log(self, message: str, level: str = "INFO") -> None:
        log_func = {
            "INFO": self.logger.info,
            "SUCCESS": self.logger.info,
            "ERROR": self.logger.error,
            "DEBUG": self.logger.debug,
            "WARNING": self.logger.warning,
        }.get(level, self.logger.info)
        prefix = ""
        if self.config.use_emojis:
            icons = {
                "INFO": "ℹ️ ",
                "SUCCESS": "✅ ",
                "ERROR": "❌ ",
                "DEBUG": "🔍 ",
                "WARNING": "⚠️ ",
            }
            prefix = icons.get(level, "")
        log_func(f"{prefix}{message}")

    def print_header(self, package_name: str, package_dir: Optional[str]):
        self.log("=" * 70, level="INFO")
        title = (
            "🔍 ADVANCED IMPORT DIAGNOSTIC TOOL V20 ⚡"
            if self.config.use_emojis
            else "ADVANCED IMPORT DIAGNOSTIC TOOL V20"
        )
        self.log(title, level="INFO")
        self.log("=" * 70, level="INFO")
        self.log(f"Target package: {package_name}", level="INFO")
        self.log(f"Python version: {sys.version.splitlines()[0]}", level="INFO")
        self.log(f"Working directory: {os.getcwd()}", level="INFO")
        if package_dir:
            self.log(f"Package dir: {package_dir}", level="INFO")
        self.log(f"Continue on error: {self.config.continue_on_error}", level="INFO")
        self.log(f"Dry run: {self.config.dry_run}", level="INFO")
        self.log(f"Safe mode: {self.config.safe_mode}", level="INFO")
        self.log(
            f"Safe-skip-imports enforced: {self.config.safe_skip_imports and self.config.safe_mode}",
            level="INFO",
        )
        self.log(f"Telemetry: {self.config.enable_telemetry}", level="INFO")
        self.log(f"Caching: {self.config.enable_cache}", level="INFO")
        self.log(f"Auto-fix generation: {self.config.generate_fixes}", level="INFO")
        if self.config.log_file:
            self.log(f"Logging to file: {self.config.log_file}", level="INFO")

    def print_summary(
        self,
        imported_modules: Set[str],
        failed_modules: List[Tuple[str, str]],
        skipped_modules: Set[str],
        timings: Dict[str, float],
        telemetry_summary: Optional[Dict],
        auto_fixes: List[AutoFix],
        discovery_errors: List[Tuple[str, str]],
        elapsed_seconds: float,
        discovery_only: bool = False,
    ) -> None:
        self.log("\n" + "=" * 70, level="INFO")
        self.log("📊 DIAGNOSTIC SUMMARY", level="INFO")
        self.log("=" * 70, level="INFO")
        total_attempted = len(imported_modules) + len(failed_modules)
        self.log(
            f"Total modules attempted (imports run): {total_attempted}", level="INFO"
        )
        self.log(f"Successful imports: {len(imported_modules)}", level="INFO")
        self.log(f"Failed imports: {len(failed_modules)}", level="INFO")
        self.log(f"Skipped modules: {len(skipped_modules)}", level="INFO")
        self.log(f"Time elapsed: {elapsed_seconds:.2f} seconds", level="INFO")
        if discovery_only:
            self.log(
                "Note: this was a discovery-only run (no imports performed).",
                level="WARNING",
            )
        if auto_fixes:
            self.log(f"Auto-fixes generated: {len(auto_fixes)}", level="INFO")

        if telemetry_summary:
            self.log("\n📈 Telemetry Summary:", level="INFO")
            self.log(f"  Total events: {telemetry_summary['total_events']}", level="INFO")
            self.log(
                f"  Avg import time: {telemetry_summary['avg_import_time_ms']:.2f}ms",
                level="INFO",
            )
            if telemetry_summary.get("slowest_imports"):
                self.log("  Slowest imports:", level="INFO")
                for item in telemetry_summary["slowest_imports"]:
                    self.log(
                        f"    - {item['module']}: {item['duration_ms']:.2f}ms",
                        level="INFO",
                    )

        if (self.config.verbose or not self.config.quiet) and timings:
            self.log("\nModule Timings (top 10):", level="INFO")
            for mod, t in sorted(
                timings.items(), key=lambda x: x[1], reverse=True
            )[:10]:
                self.log(f"  {mod}: {t:.2f}s", level="INFO")

        if failed_modules:
            self.log("\n❌ FAILED MODULES:", level="ERROR")
            for module, error in failed_modules:
                self.log(f"  • {module}: {error}", level="ERROR")

        if not failed_modules and not discovery_errors:
            self.log("\n🎉 ALL MODULES IMPORTED SUCCESSFULLY!", level="INFO")
            self.log("✨ Production-ready: No import issues detected", level="INFO")
        else:
            self.log(
                "\n❌ Issues found. Review detailed diagnostics above.", level="WARNING"
            )

        self.log("=" * 70, level="INFO")
        self.print_additional_tips()

    def print_additional_tips(self) -> None:
        self.log("\n💡 Production Best Practices:", level="INFO")
        self.log(
            " - Integrate into CI/CD: python -m importdoc PACKAGE --json --continue-on-error",
            level="INFO",
        )
        self.log(
            " - Enable telemetry in production for monitoring: --enable-telemetry",
            level="INFO",
        )
        self.log(" - Use caching for faster builds: --enable-cache", level="INFO")
        self.log(
            " - Generate automated fixes: --generate-fixes --fix-output fixes.json",
            level="INFO",
        )
        self.log(
            " - Always run in a virtualenv for peace of mind; use --no-safe-mode if you intentionally want imports.",
            level="INFO",
        )

    def print_json_summary(
        self,
        package_name: str,
        discovered_modules: Set[str],
        discovery_errors: List[Tuple[str, str]],
        imported_modules: Set[str],
        failed_modules: List[Tuple[str, str]],
        skipped_modules: Set[str],
        timings: Dict[str, float],
        package_tree: Dict[str, List[str]],
        env_info: Dict[str, bool],
        auto_fixes: List[AutoFix],
        telemetry_summary: Optional[Dict],
        elapsed_seconds: float,
        discovery_only: bool = False,
    ) -> None:
        summary = {
            "version": _package_version,
            "package": package_name,
            "discovered_modules": list(discovered_modules),
            "discovery_errors": [
                {"module": m, "error": e} for m, e in discovery_errors
            ],
            "imported_modules": list(imported_modules),
            "failed_modules": [
                {"module": m, "error": e} for m, e in failed_modules
            ],
            "skipped_modules": list(skipped_modules),
            "timings": timings,
            "module_tree": package_tree,
            "env_info": env_info,
            "elapsed_seconds": elapsed_seconds,
            "auto_fixes": [asdict(fix) for fix in auto_fixes],
            "telemetry": telemetry_summary,
            "health_check": {
                "passed": len(failed_modules) == 0,
                "total_modules": len(discovered_modules),
                "success_rate": len(imported_modules)
                / max(1, len(discovered_modules))
                if discovered_modules
                else 0.0,
                "safety_note": "Run in venv for best practices"
                if not env_info.get("virtualenv")
                else "Venv detected - good!",
                "discovery_only": discovery_only,
            },
        }
        if not validate_json(summary, JSON_SUMMARY_SCHEMA):
            self.log(
                "Summary JSON failed schema validation. Outputting anyway.",
                level="WARNING",
            )
        sys.stdout.write(json.dumps(summary, indent=2))

    def export_fixes(self, auto_fixes: List[AutoFix]):
        if not auto_fixes:
            return
        output_file = self.config.fix_output or "import_diagnostic_fixes.json"
        fixes_data = [asdict(fix) for fix in auto_fixes]
        if not validate_json(fixes_data, FIXES_SCHEMA):
            self.log(
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
            self.log(
                f"\n🔧 Generated {len(auto_fixes)} automated fixes → {output_file}",
                level="INFO",
            )
            self.log("\nAuto-Fix Summary:", level="INFO")
            for fix in auto_fixes:
                self.log(
                    f"  • {fix.issue_type}: {fix.description} (confidence: {fix.confidence:.0%})",
                    level="INFO",
                )
        except Exception as e:
            self.log(f"Failed to export fixes: {e}", level="WARNING")

    def export_graph(self, edges: Set[Tuple[str, str]], failed_modules: Set[str]):
        if not self.config.dot_file or not edges:
            return
        try:
            dot_path = Path(self.config.dot_file)
            dot_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                delete=False,
                dir=str(dot_path.parent or Path.cwd()),
                encoding="utf-8",
            ) as tf:
                tf.write("digraph imports {\n")
                tf.write("  node [shape=box, style=filled, fillcolor=lightblue];\n")
                for a, b in sorted(edges):
                    color = "red" if b in failed_modules else "green"
                    tf.write(f'  \"{a}\" -> \"{b}\" [color={color}, penwidth=2];\n')
                tf.write("}\n")
                tmp = tf.name
            os.replace(tmp, str(dot_path))
            self.log(
                f"Interactive graph written to {dot_path} - open in Graphviz.",
                level="INFO",
            )
        except Exception as e:
            self.log(f"Failed to write graph: {e}", level="WARNING")

    def diagnose_path_issue(self, module_name: str) -> None:
        from .utils import find_module_file_path
        self.log("📁 Filesystem Analysis:", level="INFO")
        file_path = find_module_file_path(module_name)
        if file_path:
            self.log(f"Found file: {file_path}", level="INFO")
            try:
                self.log(
                    f"Permissions: {oct(file_path.stat().st_mode)[-3:]}", level="INFO"
                )
            except Exception:
                pass
        else:
            self.log("No file found matching module.", level="INFO")
        self.log("Current sys.path:", level="INFO")
        for sp in sys.path:
            self.log(f"  - {sp}", level="INFO")
