from typing import List, Protocol, Any, Dict
from dataclasses import dataclass, field
import importlib
import importlib.util
import sys
from pathlib import Path

@dataclass
class PluginError:
    type: str
    message: str

class PluginContext:
    def __init__(self):
        self.errors: List[PluginError] = []
        self.data: Dict[str, Any] = {}

    def report_error(self, type: str, message: str):
        self.errors.append(PluginError(type, message))

class Plugin(Protocol):
    name: str

    def run_checks(self, context: PluginContext) -> None:
        ...

class PluginManager:
    def __init__(self, reporter=None):
        self.plugins: List[Plugin] = []
        self.reporter = reporter

    def _log(self, message: str, level: str = "INFO"):
        if self.reporter:
            self.reporter.log(message, level=level)
        else:
            # Fallback for when reporter is not available (e.g. unit tests)
            pass

    def register(self, plugin: Plugin):
        self.plugins.append(plugin)

    def load_from_config(self, plugin_paths: List[str]):
        """
        Load plugins from a list of paths or module names.
        """
        for path_str in plugin_paths:
            try:
                # Try to import as a module first
                module = None
                if path_str.endswith(".py"):
                    # Load from file path
                    path = Path(path_str).resolve()
                    # Namespace the module to avoid collisions
                    module_name = f"importdoc_plugin_{path.stem}_{hash(str(path))}"
                    spec = importlib.util.spec_from_file_location(module_name, path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                else:
                    # Load as installed module
                    module = importlib.import_module(path_str)

                # Find Plugin classes in the module
                if module:
                    found = False
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and hasattr(attr, "run_checks")
                            and hasattr(attr, "name")
                            and attr is not Plugin
                        ):
                            # Instantiate the plugin
                            try:
                                plugin_instance = attr()
                                self.register(plugin_instance)
                                found = True
                            except Exception as e:
                                self._log(f"Failed to instantiate plugin {attr_name} from {path_str}: {e}", level="ERROR")
                    if not found:
                        self._log(f"No valid plugins found in {path_str}", level="WARNING")

            except Exception as e:
                self._log(f"Failed to load plugin from {path_str}: {e}", level="ERROR")

    def run_checks(self, context: PluginContext):
        for plugin in self.plugins:
            try:
                plugin.run_checks(context)
            except Exception as e:
                # Decide how to handle plugin crashes. For now, report as error.
                context.report_error("PluginCrash", f"Plugin {getattr(plugin, 'name', 'Unknown')} crashed: {e}")
