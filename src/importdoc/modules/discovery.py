# src/importdoc/modules/discovery.py

import importlib.util
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .config import DiagnosticConfig
from .reporting import DiagnosticReporter


@dataclass
class DiscoveryResult:
    discovered_modules: Set[str]
    package_tree: Dict[str, List[str]]
    discovery_errors: List[Tuple[str, str]]
    skipped_modules: Set[str]


class ModuleDiscoverer:
    def __init__(self, config: DiagnosticConfig, reporter: DiagnosticReporter):
        self.config = config
        self.reporter = reporter
        self.skipped_modules: Set[str] = set()

    def _should_skip_module(self, module_name: str) -> bool:
        skipped = any(pat.search(module_name) for pat in self.config.exclude_regexes)
        if skipped:
            self.skipped_modules.add(module_name)
        return skipped

    def validate_package(self, package_name: str) -> bool:
        try:
            spec = importlib.util.find_spec(package_name)
            if spec is None:
                self.reporter.log(f"Package '{package_name}' not found.", level="ERROR")
                self.reporter.diagnose_path_issue(package_name)
                return False
            return True
        except Exception as e:
            self.reporter.log(f"Cannot locate package '{package_name}': {e}", level="ERROR")
            self.reporter.diagnose_path_issue(package_name)
            return False

    def discover(self, root_package: str) -> DiscoveryResult:
        discovered_modules: Set[str] = set()
        package_tree: Dict[str, List[str]] = defaultdict(list)
        discovery_errors: List[Tuple[str, str]] = []
        self.skipped_modules = set()  # Reset for new run

        processed: Set[str] = set()
        stack: List[Tuple[str, List[str]]] = [(root_package, [])]

        try:
            root_spec = importlib.util.find_spec(root_package)
            if root_spec is None:
                discovery_errors.append((root_package, "Root package not found."))
                self.reporter.log(
                    f"❌ Could not find root package '{root_package}'.", level="ERROR"
                )
                return DiscoveryResult(discovered_modules, package_tree, discovery_errors, self.skipped_modules)
            sub_locs = getattr(root_spec, "submodule_search_locations", None)
            stack[0] = (root_package, list(sub_locs) if sub_locs else [])
        except Exception as e:
            discovery_errors.append((root_package, str(e)))
            self.reporter.log(f"❌ Error locating root '{root_package}': {e}", level="ERROR")
            if not self.config.continue_on_error:
                self.reporter.log(
                    "Halting discovery due to error. Use --continue-on-error to find all issues.",
                    level="ERROR",
                )
                return DiscoveryResult(discovered_modules, package_tree, discovery_errors, self.skipped_modules)

        while stack:
            package_name, search_locations = stack.pop()
            if package_name in processed:
                continue
            processed.add(package_name)
            if not self._should_skip_module(package_name):
                discovered_modules.add(package_name)
            self.reporter.log(f"Discovered: {package_name}", level="DEBUG")

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
                            discovered_modules.add(sub_name)
                            package_tree[package_name].append(sub_name)
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
                            self.reporter.log(f"  Found package: '{sub_name}'", level="DEBUG")
                        elif entry.suffix == ".py" and entry.name != "__init__.py":
                            sub_name = f"{package_name}.{entry.stem}"
                            if self._should_skip_module(sub_name):
                                continue
                            discovered_modules.add(sub_name)
                            package_tree[package_name].append(sub_name)
                            self.reporter.log(f"  Found module: '{sub_name}'", level="DEBUG")
            except Exception as e:
                discovery_errors.append((package_name, str(e)))
                self.reporter.log(
                    f"  - ⚠️ Error exploring '{package_name}': {e}", level="WARNING"
                )
                if not self.config.continue_on_error:
                    self.reporter.log(
                        "Halting discovery due to error. Use --continue-on-error to find all issues.",
                        level="WARNING",
                    )
                    return DiscoveryResult(discovered_modules, package_tree, discovery_errors, self.skipped_modules)
        
        return DiscoveryResult(discovered_modules, package_tree, discovery_errors, self.skipped_modules)



    def path_to_module(self, path: Path) -> str:
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
