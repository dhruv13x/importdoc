# tests/modules/test_diagnostics.py

import unittest
import pytest
from dataclasses import asdict
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

from importdoc.modules.diagnostics import ImportDiagnostic
from importdoc.modules.autofix import AutoFix

def test_import_diagnostic_init():
    diagnostic = ImportDiagnostic(allow_root=True)
    # Check config object
    assert diagnostic.config.continue_on_error is False
    assert diagnostic.config.verbose is False
    assert diagnostic.config.quiet is False
    assert diagnostic.config.use_emojis is True
    assert diagnostic.config.log_file is None
    assert diagnostic.config.timeout == 0
    assert diagnostic.config.dry_run is False
    assert diagnostic.config.unload is False
    assert diagnostic.config.json_output is False
    assert diagnostic.config.parallel == 0
    assert diagnostic.config.max_depth is None
    assert diagnostic.config.dev_mode is False
    assert diagnostic.config.dev_trace is False
    assert diagnostic.config.graph is False
    assert diagnostic.config.dot_file is None
    assert diagnostic.config.show_env is False
    assert diagnostic.config.allow_root is True
    assert diagnostic.config.generate_fixes is False
    assert diagnostic.config.fix_output is None
    assert diagnostic.config.safe_mode is True
    assert diagnostic.config.safe_skip_imports is True
    assert diagnostic.config.max_scan_results == 200

@patch("importdoc.modules.runner.import_module_worker")
def test_import_discovered_modules_success(mock_import_module_worker):
    mock_import_module_worker.return_value = {"success": True, "time_ms": 10.0}

    diagnostic = ImportDiagnostic(allow_root=True)
    discovered = {"os", "sys"}
    diagnostic.runner.run_imports(discovered, Path.cwd(), None)

    assert "os" in diagnostic.runner.imported_modules
    assert "sys" in diagnostic.runner.imported_modules
    assert len(diagnostic.runner.failed_modules) == 0


@patch("importdoc.modules.runner.import_module_worker")
def test_import_discovered_modules_failure(mock_import_module_worker):
    mock_import_module_worker.return_value = {
        "success": False,
        "error": "Test error",
        "tb": "Traceback",
        "time_ms": 10.0,
    }

    diagnostic = ImportDiagnostic(allow_root=True)
    discovered = {"non_existent_module"}
    diagnostic.runner.run_imports(discovered, Path.cwd(), None)

    assert "non_existent_module" not in diagnostic.runner.imported_modules
    assert len(diagnostic.runner.failed_modules) == 1
    assert diagnostic.runner.failed_modules[0][0] == "non_existent_module"
    assert "Test error" in diagnostic.runner.failed_modules[0][1]


@patch("importdoc.modules.runner.find_module_file_path")
@patch("importdoc.modules.cache.DiagnosticCache.get")
def test_import_discovered_modules_cached(mock_cache_get, mock_find_module_file_path):
    mock_find_module_file_path.return_value = Path("/path/to/module.py")
    mock_cache_get.return_value = {"success": True, "time_ms": 10.0}

    diagnostic = ImportDiagnostic(enable_cache=True, allow_root=True)
    discovered = {"os"}
    diagnostic.runner.run_imports(discovered, Path.cwd(), None)

    assert "os" in diagnostic.runner.imported_modules
    assert len(diagnostic.runner.failed_modules) == 0


@patch("importdoc.modules.runner.import_module_worker")
def test_import_discovered_modules_parallel(mock_import_module_worker):
    mock_import_module_worker.return_value = {"success": True, "time_ms": 10.0}

    diagnostic = ImportDiagnostic(parallel=2, allow_root=True)
    discovered = {"os", "sys"}
    diagnostic.runner.run_imports(discovered, Path.cwd(), None)

    assert "os" in diagnostic.runner.imported_modules
    assert "sys" in diagnostic.runner.imported_modules
    assert len(diagnostic.runner.failed_modules) == 0

def test_handle_error_no_module_named():
    diagnostic = ImportDiagnostic(allow_root=True)
    # We need to supply context to _handle_error implicitly via state or mocks
    # But _handle_error takes args.
    # Warning: _handle_error calls reporter.log, which might fail if not mocked or if output is restricted.
    # ImportRunner delegates to processor
    diagnostic.runner.processor.set_context(Path.cwd(), None, [])
    diagnostic.runner.processor.handle_error("my_module", Exception("No module named 'my_module'"))
    assert len(diagnostic.runner.failed_modules) == 1
    assert diagnostic.runner.failed_modules[0][0] == "my_module"
    assert "No module named 'my_module'" in diagnostic.runner.failed_modules[0][1]

def test_handle_error_cannot_import_name():
    diagnostic = ImportDiagnostic(allow_root=True)
    diagnostic.runner.processor.set_context(Path.cwd(), None, [])
    diagnostic.runner.processor.handle_error(
        "my_module", Exception("cannot import name 'my_symbol' from 'my_module'")
    )
    assert len(diagnostic.runner.failed_modules) == 1
    assert diagnostic.runner.failed_modules[0][0] == "my_module"
    assert (
        "cannot import name 'my_symbol' from 'my_module'"
        in diagnostic.runner.failed_modules[0][1]
    )

def test_print_json_summary():
    diagnostic = ImportDiagnostic(json_output=True, allow_root=True)
    with patch("sys.stdout.write") as mock_stdout_write:
        diagnostic.reporter.print_json_summary(
            "my_package", set(), [], set(), [], set(), {}, {}, {}, [], None, 1.0
        )
        mock_stdout_write.assert_called_once()

def test_print_header():
    diagnostic = ImportDiagnostic(allow_root=True)
    with patch.object(diagnostic.reporter, "log") as mock_log:
        diagnostic.reporter.print_header("my_package", "/path/to/package")
        mock_log.assert_called()

def test_validate_package_success():
    diagnostic = ImportDiagnostic(allow_root=True)
    with patch("importdoc.modules.discovery.importlib.util.find_spec") as mock_find_spec:
        mock_find_spec.return_value = True
        assert diagnostic.discoverer.validate_package("my_package") is True

def test_validate_package_failure():
    diagnostic = ImportDiagnostic(allow_root=True)
    with patch("importdoc.modules.discovery.importlib.util.find_spec") as mock_find_spec:
        mock_find_spec.return_value = None
        assert diagnostic.discoverer.validate_package("non_existent_package") is False

def test_print_summary():
    diagnostic = ImportDiagnostic(allow_root=True)
    with patch.object(diagnostic.reporter, "log") as mock_log:
        diagnostic.reporter.print_summary(set(), [], set(), {}, None, [], [], 1.0)
        mock_log.assert_called()

def test_analyze_error_context_circular_import():
    diagnostic = ImportDiagnostic(allow_root=True)
    # Pass import stack manually
    import_stack = ["a", "b"]
    context = diagnostic.analyzer.analyze(
        "a", Exception("circular import"), "circular import", Path.cwd(), None, import_stack
    )
    assert context["type"] == "circular_import"
    assert "a -> b -> a" in context["auto_fix"].module_name

def test_analyze_error_context_dll_load_failed():
    diagnostic = ImportDiagnostic(allow_root=True)
    context = diagnostic.analyzer.analyze(
        "my_module", Exception("dll load failed"), "dll load failed", Path.cwd(), None, []
    )
    assert context["type"] == "shared_library"

def test_analyze_error_context_syntax_error():
    diagnostic = ImportDiagnostic(allow_root=True)
    context = diagnostic.analyzer.analyze(
        "my_module", Exception("syntaxerror"), "syntaxerror", Path.cwd(), None, []
    )
    assert context["type"] == "syntax_error"


@patch("importdoc.modules.reporting.tempfile.NamedTemporaryFile")
@patch("importdoc.modules.reporting.os.replace")
@patch("importdoc.modules.reporting.json.dump")
@patch("importdoc.modules.reporting.Path.mkdir")
def test_export_fixes_correctly(
    mock_mkdir, mock_json_dump, mock_os_replace, mock_tempfile
):
    diagnostic = ImportDiagnostic(
        generate_fixes=True, fix_output="fixes.json", continue_on_error=True, allow_root=True
    )
    fix = AutoFix(
        issue_type="missing_import",
        module_name="my_module",
        confidence=0.9,
        description="A test fix",
        patch=None,
        manual_steps=[],
    )
    # We call export_fixes on reporter
    
    # Configure the mock for NamedTemporaryFile
    mock_file = MagicMock()
    mock_file.name = "temp_file_name"
    mock_tempfile.return_value.__enter__.return_value = mock_file

    diagnostic.reporter.export_fixes([fix])

    # Assertions
    mock_mkdir.assert_called_with(parents=True, exist_ok=True)
    mock_json_dump.assert_called_once_with([asdict(fix)], mock_file, indent=2)
    mock_os_replace.assert_called_once_with("temp_file_name", "fixes.json")

def test_should_skip_module():
    diagnostic = ImportDiagnostic(exclude_patterns=[r"^_", r".*\.tests$"], allow_root=True)
    assert diagnostic.discoverer._should_skip_module("_internal") is True
    assert diagnostic.discoverer._should_skip_module("my_module.tests") is True
    assert diagnostic.discoverer._should_skip_module("my_module.public") is False


@patch("importdoc.modules.discovery.importlib.util.find_spec")
def test_discover_all_modules(mock_find_spec):
    main_spec = MagicMock()
    main_spec.submodule_search_locations = ["/path/to/my_package"]

    def find_spec_side_effect(name, *args, **kwargs):
        if name == "my_package":
            return main_spec
        return None

    mock_find_spec.side_effect = find_spec_side_effect

    with patch("importdoc.modules.discovery.Path") as mock_path_class:
        mock_path_instance = mock_path_class.return_value
        mock_path_instance.exists.return_value = True

        mock_file = MagicMock()
        mock_file.configure_mock(name="my_module.py", suffix=".py", stem="my_module")
        mock_file.is_dir.return_value = False

        mock_init = MagicMock()
        mock_init.configure_mock(name="__init__.py", suffix=".py", stem="__init__")
        mock_init.is_dir.return_value = False

        mock_path_instance.iterdir.return_value = [mock_file, mock_init]

        diagnostic = ImportDiagnostic(allow_root=True)
        result = diagnostic.discoverer.discover("my_package")

    assert "my_package" in result.discovered_modules
    assert "my_package.my_module" in result.discovered_modules


@patch("importdoc.modules.discovery.importlib.util.find_spec")
def test_discover_all_modules_root_not_found(mock_find_spec):
    mock_find_spec.return_value = None
    diagnostic = ImportDiagnostic(allow_root=True)
    result = diagnostic.discoverer.discover("non_existent_package")
    assert len(result.discovery_errors) == 1
    assert "Root package not found" in result.discovery_errors[0][1]


@patch("importdoc.modules.utils.find_module_file_path")


def test_diagnose_path_issue(mock_find_module_file_path):


    mock_find_module_file_path.return_value = None


    diagnostic = ImportDiagnostic(allow_root=True)


    with patch.object(diagnostic.reporter, "log") as mock_log:


        diagnostic.reporter.diagnose_path_issue("my_module")


        mock_log.assert_any_call("📁 Filesystem Analysis:", level="INFO")








def test_install_uninstall_import_tracer():
    diagnostic = ImportDiagnostic(allow_root=True)
    original_import = __builtins__["__import__"]
    diagnostic.runner._install_import_tracer()
    assert __builtins__["__import__"] != original_import
    diagnostic.runner._uninstall_import_tracer()
    assert __builtins__["__import__"] == original_import


@patch("importdoc.modules.reporting.tempfile.NamedTemporaryFile")
@patch("importdoc.modules.reporting.os.replace")
@patch("importdoc.modules.reporting.Path.mkdir")
def test_export_graph(mock_mkdir, mock_os_replace, mock_tempfile):
    diagnostic = ImportDiagnostic(dot_file="graph.dot", allow_root=True)
    edges = {("a", "b"), ("b", "c")}

    mock_file = MagicMock()
    mock_file.name = "temp_graph_name"
    mock_file.write.return_value = None
    mock_tempfile.return_value.__enter__.return_value = mock_file

    diagnostic.reporter.export_graph(edges, set())

    mock_mkdir.assert_called_with(parents=True, exist_ok=True)
    # We check write calls.
    mock_file.write.assert_any_call("digraph imports {\n")
    mock_os_replace.assert_called_once_with("temp_graph_name", "graph.dot")


@patch("importdoc.modules.discovery.ModuleDiscoverer.validate_package", return_value=False)
def test_run_diagnostic_package_not_found(mock_validate_package):
    diagnostic = ImportDiagnostic(allow_root=True)
    result = diagnostic.run_diagnostic("non_existent_package")
    assert result is False


@patch("importdoc.modules.discovery.ModuleDiscoverer.validate_package", return_value=True)
@patch("importdoc.modules.discovery.ModuleDiscoverer.discover")
def test_run_diagnostic_with_package_dir(mock_discover, mock_validate_package):
    # Mock discover result
    from importdoc.modules.discovery import DiscoveryResult
    mock_discover.return_value = DiscoveryResult(set(), {}, [], set())

    diagnostic = ImportDiagnostic(allow_root=True)
    with patch("sys.path", []) as mock_sys_path:
        diagnostic.run_diagnostic("my_package", package_dir="/path/to/my_package")
        assert "/path/to" in mock_sys_path


@patch("importdoc.modules.discovery.ModuleDiscoverer.validate_package", return_value=True)
@patch("importdoc.modules.discovery.ModuleDiscoverer.discover")
@patch("importdoc.modules.runner.ImportRunner.run_imports")
def test_run_diagnostic_skip_imports_enforced(
    mock_run_imports, mock_discover, mock_validate_package
):
    from importdoc.modules.discovery import DiscoveryResult
    mock_discover.return_value = DiscoveryResult(set(), {}, [], set())

    diagnostic = ImportDiagnostic(allow_root=True)
    diagnostic._skip_imports_enforced_by_safe_mode = True
    diagnostic.run_diagnostic("my_package")
    mock_run_imports.assert_not_called()

def test_print_summary_with_failed_modules():
    diagnostic = ImportDiagnostic(allow_root=True)
    failed_modules = [("my_module", "Test error")]
    with patch.object(diagnostic.reporter, "log") as mock_log:
        diagnostic.reporter.print_summary(set(), failed_modules, set(), {}, None, [], [], 1.0)
        mock_log.assert_any_call("\n❌ FAILED MODULES:", level="ERROR")
        mock_log.assert_any_call("  • my_module: Test error", level="ERROR")


@patch("importdoc.modules.telemetry.TelemetryCollector.get_summary")
def test_print_summary_with_telemetry(mock_get_summary):
    diagnostic = ImportDiagnostic(enable_telemetry=True, allow_root=True)
    summary = {
        "total_events": 1,
        "avg_import_time_ms": 10.0,
        "slowest_imports": [{"module": "my_module", "duration_ms": 10.0}],
    }
    with patch.object(diagnostic.reporter, "log") as mock_log:
        diagnostic.reporter.print_summary(set(), [], set(), {}, summary, [], [], 1.0)
        mock_log.assert_any_call("\n📈 Telemetry Summary:", level="INFO")

def test_print_additional_tips():
    diagnostic = ImportDiagnostic(allow_root=True)
    with patch.object(diagnostic.reporter, "log") as mock_log:
        diagnostic.reporter.print_additional_tips()
        mock_log.assert_any_call("\n💡 Production Best Practices:", level="INFO")


@patch("importdoc.modules.reporting.logging.Logger.info")
def test_log_with_emojis(mock_logger_info):
    diagnostic = ImportDiagnostic(use_emojis=True, allow_root=True)
    diagnostic.reporter.log("Test message", level="INFO")
    mock_logger_info.assert_called_with("ℹ️ Test message")


@patch("importdoc.modules.reporting.logging.Logger.info")
def test_log_without_emojis(mock_logger_info):
    diagnostic = ImportDiagnostic(use_emojis=False, allow_root=True)
    diagnostic.reporter.log("Test message", level="INFO")
    mock_logger_info.assert_called_with("Test message")


@patch("importdoc.modules.reporting.logging.getLogger")
def test_setup_logger(mock_get_logger):
    diagnostic = ImportDiagnostic(allow_root=True)
    # _setup_logger is private but we can test it via init or direct call
    logger = diagnostic.reporter._setup_logger(None, 1)
    mock_get_logger.assert_called_with("import_diagnostic")


@patch("importdoc.modules.reporting.logging.getLogger")
@patch("importdoc.modules.reporting.RotatingFileHandler")
def test_setup_logger_with_file(mock_file_handler, mock_get_logger):
    # Clean up any previous logger setup? The logger is cached in the module?
    # The reporter method checks `logger._initialized_by_import_diag`.
    # We need a fresh logger mock.
    mock_logger = MagicMock()
    delattr(mock_logger, "_initialized_by_import_diag") if hasattr(mock_logger, "_initialized_by_import_diag") else None
    mock_get_logger.return_value = mock_logger

    diagnostic = ImportDiagnostic(log_file="test.log", allow_root=True)
    mock_file_handler.assert_called_with("test.log", maxBytes=5 * 1024 * 1024, backupCount=5)


@patch("os.geteuid", return_value=0)
def test_init_as_root_without_allow_root(mock_geteuid):
    with patch("os.name", "posix"):
        with pytest.raises(PermissionError):
            ImportDiagnostic(allow_root=False)


@patch("os.geteuid", return_value=0)
def test_init_as_root_with_allow_root(mock_geteuid):
    with patch("os.name", "posix"):
        try:
            ImportDiagnostic(allow_root=True)
        except PermissionError:
            pytest.fail("PermissionError raised unexpectedly")

def test_process_import_result_success():
    diagnostic = ImportDiagnostic(allow_root=True)
    result = {"success": True, "time_ms": 10.0}
    diagnostic.runner.processor.process_result("my_module", result)
    assert "my_module" in diagnostic.runner.imported_modules

def test_process_import_result_failure():
    diagnostic = ImportDiagnostic(allow_root=True)
    result = {"success": False, "error": "Test error", "tb": "Traceback"}
    # Need to patch handle_error on processor
    with patch.object(diagnostic.runner.processor, "handle_error") as mock_handle_error:
        diagnostic.runner.processor.process_result("my_module", result)
        mock_handle_error.assert_called_once()


@patch("importdoc.modules.analysis.importlib.util.find_spec")
def test_analyze_error_context_no_module_named_local_submodule(mock_find_spec):
    def find_spec_side_effect(name):
        if name == "my_package":
            return True
        return True # assume root parent exists

    mock_find_spec.side_effect = find_spec_side_effect
    diagnostic = ImportDiagnostic(allow_root=True)
    # ErrorAnalyzer needs project_root and current_package passed to analyze
    context = diagnostic.analyzer.analyze(
        "my_package.sub_module",
        Exception("no module named 'my_package.sub_module'"),
        "no module named 'my_package.sub_module'",
        Path.cwd(),
        "my_package",
        []
    )
    assert context["type"] == "local_submodule"


@patch("importdoc.modules.analysis.find_module_file_path")
def test_analyze_error_context_cannot_import_name(mock_find_module_file_path):
    mock_path = MagicMock()
    mock_path.read_text.return_value = "import my_symbol"
    mock_find_module_file_path.return_value = mock_path
    diagnostic = ImportDiagnostic(allow_root=True)
    context = diagnostic.analyzer.analyze(
        "my_module",
        Exception("cannot import name 'my_symbol' from 'my_module'"),
        "cannot import name 'my_symbol' from 'my_module'",
        Path.cwd(),
        None,
        []
    )
    assert context["type"] == "missing_name"


@patch("importdoc.modules.analysis.is_standard_lib")
@patch("importdoc.modules.analysis.suggest_pip_names", return_value=["my_package"])
def test_analyze_error_context_no_module_named_external_dependency(
    mock_suggest_pip_names, mock_is_standard_lib
):
    mock_is_standard_lib.return_value = False
    diagnostic = ImportDiagnostic(allow_root=True)
    context = diagnostic.analyzer.analyze(
        "my_package",
        Exception("no module named 'my_package'"),
        "no module named 'my_package'",
        Path.cwd(),
        None,
        []
    )
    assert context["type"] == "external_dependency"


@patch("importdoc.modules.analysis.is_standard_lib")
def test_analyze_error_context_no_module_named_standard_lib(mock_is_standard_lib):
    mock_is_standard_lib.return_value = True
    diagnostic = ImportDiagnostic(allow_root=True)
    context = diagnostic.analyzer.analyze(
        "my_module",
        Exception("no module named 'my_module'"),
        "no module named 'my_module'",
        Path.cwd(),
        None,
        []
    )
    assert context["type"] == "standard_library"

def test_analyze_error_context_incomplete_import():
    diagnostic = ImportDiagnostic(allow_root=True)
    tb_str = "import ("
    context = diagnostic.analyzer.analyze(
        "my_module",
        Exception("incomplete import"),
        tb_str,
        Path.cwd(),
        None,
        [],
    )
    assert context["type"] == "incomplete_import"


@patch("importdoc.modules.analysis.is_standard_lib", return_value=False)
def test_analyze_error_context_no_module_named_local_module(mock_is_standard_lib):
    diagnostic = ImportDiagnostic(allow_root=True)
    context = diagnostic.analyzer.analyze(
        "my_package.my_module",
        Exception("no module named 'my_package.my_module'"),
        "no module named 'my_package.my_module'",
        Path.cwd(),
        "my_package",
        []
    )
    assert context["type"] == "local_module"

class TestDiagnostics(unittest.TestCase):
    def test_import_diagnostic_init(self):
        diagnostic = ImportDiagnostic(allow_root=True)
        self.assertIsNotNone(diagnostic)

    def test_run_diagnostic_success(self):
        diagnostic = ImportDiagnostic(allow_root=True)
        # We need to mock discoverer and runner for a success case without side effects?
        # Or just let it fail discovery of "os" if it's not a package?
        # "os" is a module. discovery might fail if we look for package "os".
        # ModuleDiscoverer.discover("os") might return "os" in discovered_modules.
        # But run_diagnostic expects to be able to find the package spec.
        # For "os", find_spec works.
        with patch.object(diagnostic.discoverer, "discover") as mock_discover:
             from importdoc.modules.discovery import DiscoveryResult
             mock_discover.return_value = DiscoveryResult({"os"}, {"os":[]}, [], set())
             with patch.object(diagnostic.runner, "run_imports") as mock_run:
                 # mock runner to not fail
                 # We need to set failed_modules on the processor since runner delegates to it
                 diagnostic.runner.processor.failed_modules = []
                 success = diagnostic.run_diagnostic("os")
                 self.assertTrue(success)

    def test_run_diagnostic_failure(self):
        diagnostic = ImportDiagnostic(allow_root=True)
        # validate package fails
        with patch.object(diagnostic.discoverer, "validate_package", return_value=False):
            success = diagnostic.run_diagnostic("non_existent_module")
            self.assertFalse(success)

if __name__ == "__main__":
    unittest.main()
