# src/importdoc/modules/processor.py

import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Set, Tuple

from .analysis import ErrorAnalyzer
from .cache import DiagnosticCache
from .config import DiagnosticConfig
from .reporting import DiagnosticReporter
from .telemetry import TelemetryCollector
from .utils import find_module_file_path


class ResultProcessor:
    """
    Handles processing of import results, including success/failure handling,
    caching, telemetry recording, and error reporting.
    """

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

        # State that accumulates over time
        self.imported_modules: Set[str] = set()
        self.failed_modules: List[Tuple[str, str]] = []
        self.timings: Dict[str, float] = {}
        self.auto_fixes: List[Any] = []  # List[AutoFix]

        # Context required for analysis
        self.project_root = None
        self.current_package = None
        self.import_stack = []

    def set_context(self, project_root, current_package, import_stack):
        self.project_root = project_root
        self.current_package = current_package
        self.import_stack = import_stack

    def process_result(self, mod: str, result: Dict) -> None:
        """
        Process a single import result (success or failure).
        """
        elapsed = result.get("time_ms", 0.0)
        self.timings[mod] = elapsed / 1000.0

        if result.get("success"):
            self._handle_success(mod, result, elapsed)
        else:
            self._handle_failure(mod, result, elapsed)

    def _handle_success(self, mod: str, result: Dict, elapsed: float) -> None:
        self.imported_modules.add(mod)
        self.reporter.log(f"SUCCESS: Imported '{mod}' ({elapsed:.0f}ms)", level="SUCCESS")

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

    def _handle_failure(self, mod: str, result: Dict, elapsed: float) -> None:
        error_msg = result.get("error", "<error>")
        tb_str = result.get("tb")

        if self.cache:
            self.cache.set(
                mod,
                find_module_file_path(mod),
                {
                    "success": False,
                    "error": error_msg,
                    "time_ms": elapsed,
                },
            )

        self.telemetry.record(
            "import_failure", mod, elapsed, error=error_msg
        )

        err = Exception(error_msg)
        self.handle_error(mod, err, tb_str=tb_str)

    def handle_error(
        self,
        module_name: str,
        error: Exception,
        tb_str: Optional[str] = None,
    ) -> None:
        """
        Analyze and report an error.
        """
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
            self.import_stack,
        )

        self._report_analysis(context, tb_str)
        self.reporter.diagnose_path_issue(module_name)

    def _report_analysis(self, context: Dict, tb_str: Optional[str]) -> None:
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

        # If needed, can pass module_name if it was part of context, or let caller handle specifics.
        # But 'module_name' isn't in context by default unless we add it.
        # The original code just logged diagnose_path_issue separately or not at all clearly in the main flow.
        # The analyzer context doesn't have module name usually.
        # But handle_error has module_name.
        # I'll rely on the caller or just skip calling diagnose_path_issue inside report_analysis
        # and instead call it in handle_error.
        pass

        self.reporter.log("\n--- START OF FULL TRACEBACK ---", level="INFO")
        self.reporter.log(tb_str or traceback.format_exc(), level="INFO")
        self.reporter.log("--- END OF FULL TRACEBACK ---", level="INFO")
        self.reporter.log("=" * 70 + "\n", level="ERROR")
