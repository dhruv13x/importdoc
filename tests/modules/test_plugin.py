
import pytest
from unittest.mock import MagicMock
from importdoc.modules.plugin import PluginManager, PluginContext
from importdoc.modules.runner import ImportRunner
from importdoc.modules.config import DiagnosticConfig

def test_plugin_execution():
    class TestPlugin:
        name = "TestPlugin"

        def run_checks(self, context: PluginContext):
            context.report_error("TestError", "This is a test error")

    manager = PluginManager()
    plugin = TestPlugin()
    manager.register(plugin)

    context = PluginContext()
    manager.run_checks(context)

    assert len(context.errors) == 1
    assert context.errors[0].type == "TestError"
    assert context.errors[0].message == "This is a test error"

def test_banned_imports_plugin():
    class BannedImportsPlugin:
        name = "BannedImportsPlugin"
        def __init__(self, banned_modules):
            self.banned_modules = banned_modules

        def run_checks(self, context: PluginContext):
            discovered = context.data.get("discovered_modules", [])
            for mod in discovered:
                if mod in self.banned_modules:
                    context.report_error("BannedImport", f"Module {mod} is banned.")

    plugin = BannedImportsPlugin(banned_modules=["unsafe_module"])
    manager = PluginManager()
    manager.register(plugin)

    context = PluginContext()
    context.data["discovered_modules"] = {"safe_module", "unsafe_module"}

    manager.run_checks(context)

    assert len(context.errors) == 1
    assert context.errors[0].type == "BannedImport"
    assert "unsafe_module" in context.errors[0].message

def test_plugin_logging():
    reporter = MagicMock()
    manager = PluginManager(reporter=reporter)
    manager.load_from_config(["non_existent_plugin.py"])
    reporter.log.assert_called()
    call_args = reporter.log.call_args[0]
    assert "Failed to load plugin" in call_args[0]

def test_plugin_context_data():
    context = PluginContext()
    context.data["import_edges"] = {("a", "b"), ("b", "c")}

    class EdgeCheckerPlugin:
        name = "EdgeChecker"
        def run_checks(self, context: PluginContext):
            edges = context.data.get("import_edges", set())
            if ("a", "b") in edges:
                 context.report_error("FoundEdge", "Edge a->b found")

    manager = PluginManager()
    plugin = EdgeCheckerPlugin()
    manager.register(plugin)

    manager.run_checks(context)
    assert len(context.errors) == 1
    assert context.errors[0].type == "FoundEdge"

def test_runner_integration():
    # Setup mocks
    config = DiagnosticConfig()
    config.plugins = [] # No actual plugin loading from config for this test
    reporter = MagicMock()
    analyzer = MagicMock()
    telemetry = MagicMock()
    cache = MagicMock()

    runner = ImportRunner(config, reporter, analyzer, telemetry, cache)

    # Register a plugin manually to the runner's manager
    class IntegrationTestPlugin:
        name = "IntegrationTestPlugin"
        def run_checks(self, context: PluginContext):
             context.report_error("IntegrationError", "Integration works")

    plugin = IntegrationTestPlugin()
    runner.plugin_manager.register(plugin)

    # Run imports (empty)
    # We mock run_imports behavior or just run it with empty set
    discovered = set()
    project_root = MagicMock()

    # run_imports returns False if plugins fail (since continue_on_error is False by default)
    result = runner.run_imports(discovered, project_root, None)

    assert result is False
    assert reporter.log.call_count > 0
    # Check if plugin error was logged
    found_log = False
    for call in reporter.log.call_args_list:
        if "PLUGIN ERROR" in call[0][0] and "IntegrationError" in call[0][0]:
            found_log = True
            break
    assert found_log
