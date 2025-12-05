# src/importdoc/modules/analysis.py

import ast
import difflib
import re
import sys
import traceback
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .autofix import FixGenerator
from .config import DiagnosticConfig
from .confidence import ConfidenceCalculator
from .utils import (
    analyze_ast_symbols,
    find_import_usages_in_repo,
    find_module_file_path,
    find_similar_modules,
    find_symbol_definitions_in_repo,
    is_standard_lib,
    safe_read_text,
    suggest_pip_names,
)

def _format_evidence_item(path: Path, lineno: int, kind: str) -> str:
    try:
        rel = path.relative_to(Path.cwd())
    except Exception:
        rel = path
    return f"{rel}:{lineno}: {kind}"

class ErrorAnalyzer:
    def __init__(self, config: DiagnosticConfig):
        self.config = config

    def analyze(
        self,
        module_name: str,
        error: Exception,
        tb_str: Optional[str],
        project_root: Path,
        current_package: Optional[str],
        import_stack: List[str],
    ) -> Dict:
        original_error = str(error)
        error_str = original_error.lower()
        context: Dict[str, Any] = {
            "type": "unknown",
            "suggestions": [],
            "evidence": [],
            "auto_fix": None,
            "similar_modules": [],
            "module_name": module_name, # Add module_name to context for easier access
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
            self._handle_no_module_named(context, original_error, module_name, module_path, project_root, current_package)
        elif "cannot import name" in error_str:
            self._handle_cannot_import_name(context, original_error, module_name, project_root, import_stack)
        elif "circular import" in error_str:
            self._handle_circular_import(context, module_name, import_stack)
        elif isinstance(error, AttributeError) or "attribute" in error_str:
            self._handle_attribute_error(context, original_error, module_name, module_path)
        elif any(k in error_str for k in ["dll load failed", "shared object", ".so", ".dll"]):
            self._handle_shared_library_error(context)
        elif "syntaxerror" in error_str:
            self._handle_syntax_error(context)

        # New: Check for incomplete import in traceback
        if tb_str and re.search(r"import\s*\(", tb_str):
            if context["type"] == "unknown":
                context["type"] = "incomplete_import"
            context["evidence"].append(
                "Incomplete import statement detected (missing closing parenthesis or symbols)"
            )
            context["suggestions"].append(
                "Complete the import statement with ) and the required symbols"
            )

        # Final cleanup: Limit total suggestions to avoid overwhelming the user
        seen_suggestions = set()
        final_suggestions = []
        for s in context["suggestions"]:
            if s not in seen_suggestions:
                seen_suggestions.add(s)
                final_suggestions.append(s)
        
        context["suggestions"] = final_suggestions[:5]

        return context

    def _handle_no_module_named(
        self,
        context: Dict,
        original_error: str,
        module_name: str,
        module_path: Optional[Path],
        project_root: Path,
        current_package: Optional[str],
    ):
        missing_match = re.search(
            r"no module named ['\"]?([^'\"]+)['\"]?", original_error, re.IGNORECASE
        )
        if missing_match:
            missing_mod = missing_match.group(1)
            if module_path:
                context["evidence"].insert(0, "Error likely from inner import failure.")
                context["suggestions"].insert(0, f"Fix import statements in {module_path}")
        else:
            missing_mod = module_name

        base_mod = ".".join(missing_mod.split(".")[:-1])
        is_submodule_of_existing_parent = False

        if base_mod:
            try:
                if importlib.util.find_spec(base_mod) is not None:
                    is_submodule_of_existing_parent = True
            except Exception as e:
                context["evidence"].append(f"Failed to check parent module: {type(e).__name__}: {e}")

        if is_submodule_of_existing_parent:
            context["type"] = "local_submodule"
            context["suggestions"].extend([
                f"Create missing submodule '{missing_mod}' in package '{base_mod}'",
                f"Expected path: {missing_mod.replace('.', '/')}.py or {missing_mod.replace('.', '/')}/__init__.py",
                "Check for typos in import statements",
                "Verify module exists in correct location",
            ])
            context["evidence"].append(f"Parent module '{base_mod}' exists.")
        elif current_package and missing_mod.startswith(current_package + "."):
            context["type"] = "local_module"
            context["suggestions"].extend([
                f"Create missing local module: {missing_mod}",
                f"Expected path: {missing_mod.replace(current_package + '.', '').replace('.', '/')}.py or {missing_mod.replace(current_package + '.', '').replace('.', '/')}/__init__.py",
                "Check for typos in import statements",
                "Verify module exists in correct location",
            ])
            context["evidence"].append(f"Belongs to package '{current_package}'")
        elif is_standard_lib(missing_mod.split(".")[0]):
            context["type"] = "standard_library"
            context["suggestions"].extend([
                f"Check Python installation for '{missing_mod}'",
                "Verify version compatibility",
                "Check spelling/case",
            ])
        else:
            context["type"] = "external_dependency"
            pips = suggest_pip_names(missing_mod)
            if pips:
                context["suggestions"].append(f"pip install {pips[0]}")
            context["suggestions"].extend([
                "Check requirements.txt/setup.py",
                "Verify installed in current env",
            ])
            if pips:
                context["auto_fix"] = FixGenerator.generate_missing_dependency_fix(missing_mod, pips[0])

        # Fuzzy search for similar modules
        if project_root:
             similars = find_similar_modules(
                 project_root, missing_mod, self.config.max_scan_results // 10
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

    def _handle_cannot_import_name(
        self,
        context: Dict,
        original_error: str,
        module_name: str,
        project_root: Path,
        import_stack: List[str],
    ):
        name_match = re.search(
            r"cannot import name ['\"]?([^'\"]+)['\"]? from ['\"]?([^'\"]+)['\"]?",
            original_error,
        )
        if name_match:
            name, from_mod = name_match.groups()
            context["type"] = "missing_name"
            context["suggestions"].extend([
                f"Check if '{name}' defined in '{from_mod}'",
                "Verify spelling/case",
                "Check circular dependencies",
            ])

            source_path = find_module_file_path(from_mod)
            if source_path:
                self._analyze_ast_for_name(context, source_path, name, module_name, import_stack)

            try:
                self._scan_repo_for_name(context, name, from_mod, project_root)
            except Exception as e:
                context["evidence"].append(f"Repo scan failed: {e} (tool continued safely)")

    def _analyze_ast_for_name(
        self,
        context: Dict,
        source_path: Path,
        name: str,
        module_name: str,
        import_stack: List[str],
    ):
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
                if import_stack:
                    context["auto_fix"] = FixGenerator.generate_circular_import_fix(
                        import_stack + [module_name]
                    )
            else:
                context["evidence"].append(f"'{name}' not found in AST of {source_path}.")
            if symbols.get("all"):
                context["evidence"].append(f"__all__: {symbols['all']}")

            # Fuzzy match for typo suggestions
            all_symbols = set()
            for k in ["functions", "classes", "assigns"]:
                all_symbols.update(symbols.get(k, set()))

            matches = difflib.get_close_matches(name, all_symbols, n=3, cutoff=0.7)
            for match in matches:
                context["suggestions"].append(f"Did you mean '{match}'?")

    def _scan_repo_for_name(self, context: Dict, name: str, from_mod: str, project_root: Path):
        repo_root = project_root
        if not repo_root:
             return

        defs = find_symbol_definitions_in_repo(
            repo_root, name, self.config.max_scan_results // 4
        )

        usages = find_import_usages_in_repo(
            repo_root,
            name,
            from_module=from_mod,
            max_results=self.config.max_scan_results,
        )

        correct_module = None
        potential_imports = []

        if defs:
            for p, ln, kind in defs:
                context["evidence"].append(_format_evidence_item(p, ln, kind))
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

                            priority = 0
                            if "test" in mod.lower():
                                priority += 10
                            priority += len(parts)

                            potential_imports.append((priority, mod))
                            break
                        except Exception:
                            pass
                except Exception:
                    pass
        else:
            context["evidence"].append(f"No definition of '{name}' found in repo (AST scan).")

        potential_imports.sort(key=lambda x: x[0])
        unique_mods = []
        seen_mods = set()
        for _, mod in potential_imports:
            if mod not in seen_mods and mod != from_mod:
                seen_mods.add(mod)
                unique_mods.append(mod)

        for mod in unique_mods[:3]:
            suggestion = f"Possible correct import: from {mod} import {name}"
            if suggestion not in context["suggestions"]:
                context["suggestions"].insert(0, suggestion)
            if not correct_module:
                correct_module = mod

        if usages:
            for p, ln, kind in usages:
                context["evidence"].append(_format_evidence_item(p, ln, kind))

        if correct_module and correct_module != from_mod:
            context["auto_fix"] = FixGenerator.generate_missing_import_fix(
                from_mod, name, correct_module
            )

    def _handle_circular_import(self, context: Dict, module_name: str, import_stack: List[str]):
        context["type"] = "circular_import"
        context["suggestions"] = [
            "Refactor to break cycle",
            "Use lazy imports",
            "Restructure modules",
        ]
        if import_stack:
            context["evidence"].append(f"Chain: {" -> ".join(import_stack)}")
            context["auto_fix"] = FixGenerator.generate_circular_import_fix(
                import_stack + [module_name]
            )

    def _handle_attribute_error(self, context: Dict, original_error: str, module_name: str, module_path: Optional[Path]):
        context["type"] = "attribute_error"
        attr_match = re.search(r"attribute ['\"]?([^'\"]+)['\"]?", original_error)
        attr_name = attr_match.group(1) if attr_match else None

        if is_standard_lib(module_name) and module_path:
            context["type"] = "shadowing_stdlib"
            context["evidence"].append(f"Shadows standard library module '{module_name}'")
            context["suggestions"].extend([
                f"Rename your local file '{module_path.name}' to avoid conflict",
                "Do not use standard library names for local modules"
            ])

        if attr_name:
            context["suggestions"].append(f"Check if '{attr_name}' is defined in '{module_name}'")

    def _handle_shared_library_error(self, context: Dict):
        context["type"] = "shared_library"
        context["suggestions"] = [
            "Install system libraries",
            "Set LD_LIBRARY_PATH/PATH",
            "Check architecture (32/64-bit)",
        ]

    def _handle_syntax_error(self, context: Dict):
        context["type"] = "syntax_error"
        context["suggestions"] = [
            "Fix syntax in file",
            "Check Python version compatibility",
        ]

    def calculate_confidence(self, context: Dict) -> Tuple[int, str]:
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
            "fuzzy_match": len(context.get("similar_modules", [])),
        }
        return ConfidenceCalculator.calculate(
            evidence_weights, len(context.get("suggestions", []))
        )

    def parse_tb_for_import(
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
