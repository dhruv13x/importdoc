# src/importdoc/modules/utils.py

import ast
import difflib
import importlib
import importlib.resources
import importlib.util
import os
import sys
import sysconfig
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import importlib.metadata as importlib_metadata
except Exception:
    importlib_metadata = None


def safe_read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (IOError, UnicodeDecodeError):
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return None


def analyze_ast_symbols(file_path: Path) -> Dict[str, Any]:
    results = {
        "functions": set(),
        "classes": set(),
        "assigns": set(),
        "all": None,
        "error": None,
    }
    src = safe_read_text(file_path)
    if src is None:
        results["error"] = "Could not read file."
        return results
    try:
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                results["functions"].add(node.name)
            elif isinstance(node, ast.ClassDef):
                results["classes"].add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        results["assigns"].add(t.id)
                        if t.id == "__all__":
                            try:
                                values = []
                                if isinstance(node.value, (ast.List, ast.Tuple)):
                                    for elt in node.value.elts:
                                        if isinstance(elt, ast.Constant) and isinstance(
                                            elt.value, str
                                        ):
                                            values.append(elt.value)
                                        else:
                                            values = "unsupported"  # type: ignore
                                            break
                                else:
                                    values = "unsupported"
                                results["all"] = values
                            except Exception:
                                results["all"] = "unsupported"
    except SyntaxError as e:
        results["error"] = f"SyntaxError on line {e.lineno}"
    except Exception as e:
        results["error"] = str(e)
    return results


def find_module_file_path(module_name: str) -> Optional[Path]:
    # Try importlib.util.find_spec first
    try:
        spec = importlib.util.find_spec(module_name)
        if spec and getattr(spec, "origin", None):
            origin = spec.origin
            if origin and os.path.exists(origin):
                return Path(origin)
    except Exception:
        pass

    # Try importlib.resources for packages (defensive)
    try:
        try:
            res = importlib.resources.files(module_name)
            candidate = res / "__init__.py"
            with importlib.resources.as_file(candidate) as p:
                if p.exists():
                    return Path(p)
        except Exception:
            pass
    except Exception:
        pass

    # Fallback: scan sys.path
    parts = module_name.split(".")
    for sp in sys.path:
        if not sp:
            continue
        try:
            base = Path(sp)
        except Exception:
            continue
        potential_pkg = base.joinpath(*parts)
        init_py = potential_pkg / "__init__.py"
        if init_py.is_file():
            return init_py
        module_py = base.joinpath(*parts).with_suffix(".py")
        if module_py.is_file():
            return module_py
    return None


def suggest_pip_names(module_name: str) -> List[str]:
    base = module_name.split(".")[0].lower()
    candidates = [base, base.replace("_", "-")]
    if importlib_metadata:
        try:
            dists = [
                d.metadata.get("Name", "").lower()
                for d in importlib_metadata.distributions()
            ]
            similar = [d for d in dists if base in d]
            candidates.extend(similar[:3])
        except Exception:
            pass
    # unique
    seen = []
    for c in candidates:
        if c and c not in seen:
            seen.append(c)
    return seen


def is_standard_lib(module_name: str) -> bool:
    return module_name in sys.stdlib_module_names


def detect_env() -> Dict[str, bool]:
    try:
        is_venv = hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        )
    except Exception:
        is_venv = False
    is_editable = any(
        "editable" in (p or "") for p in sys.path if p and "site-packages" in p
    )
    return {"virtualenv": is_venv, "editable": is_editable}


def _is_ignored_path(p: Path) -> bool:
    s = str(p).lower()
    ignored = [
        "site-packages",
        os.sep + ".venv" + os.sep,
        os.sep + "venv" + os.sep,
        os.sep + ".git" + os.sep,
        os.sep + "__pycache__" + os.sep,
        ".egg-info",
        os.sep + "build" + os.sep,
        os.sep + "dist" + os.sep,
    ]
    return any(x in s for x in ignored)


def find_symbol_definitions_in_repo(
    project_root: Path, symbol: str, max_results: int = 50
) -> List[Tuple[Path, int, str]]:
    results: List[Tuple[Path, int, str]] = []
    if not project_root.exists():
        return results
    try:
        for path in project_root.rglob("*.py"):
            if _is_ignored_path(path):
                continue
            src = safe_read_text(path)
            if not src:
                continue
            try:
                tree = ast.parse(src)
            except Exception:
                continue
            for node in tree.body:
                if len(results) >= max_results:
                    break
                if isinstance(node, ast.ClassDef) and node.name == symbol:
                    results.append((path, node.lineno, "class"))
                elif (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == symbol
                ):
                    results.append((path, node.lineno, "function"))
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == symbol:
                            results.append((path, node.lineno, "assign"))
                            if len(results) >= max_results:
                                break
            if len(results) >= max_results:
                break
    except Exception:
        pass
    return results


def find_import_usages_in_repo(
    project_root: Path,
    symbol: str,
    from_module: Optional[str] = None,
    max_results: int = 200,
) -> List[Tuple[Path, int, str]]:
    results: List[Tuple[Path, int, str]] = []
    if not project_root.exists():
        return results
    try:
        for path in project_root.rglob("*.py"):
            if _is_ignored_path(path):
                continue
            src = safe_read_text(path)
            if not src:
                continue
            try:
                tree = ast.parse(src)
            except Exception:
                continue
            imports_map: Dict[str, str] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if from_module and not (
                        mod == from_module or mod.startswith(from_module + ".")
                    ):
                        continue
                    for alias in node.names:
                        if alias.name == "*":
                            results.append(
                                (path, node.lineno, f"star-import from {mod}")
                            )
                        elif alias.name == symbol:
                            results.append(
                                (
                                    path,
                                    node.lineno,
                                    f"from-import {mod} import {symbol}",
                                )
                            )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == symbol:
                            results.append(
                                (path, node.lineno, f"import {symbol}")
                            )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        full_mod = alias.name
                        asname = alias.asname or full_mod.split(".")[0]
                        imports_map[asname] = full_mod
                if (
                    isinstance(node, ast.Attribute)
                    and getattr(node, "attr", None) == symbol
                ):
                    base = node.value
                    if isinstance(base, ast.Name):
                        base_name = base.id
                        mapped = imports_map.get(base_name)
                        if mapped:
                            results.append(
                                (
                                    path,
                                    node.lineno,
                                    f"attr-usage {mapped}.{symbol} (via {base_name})",
                                )
                            )
                        else:
                            results.append(
                                (path, node.lineno, f"attr-usage {base_name}.{symbol}")
                            )
                    elif isinstance(base, ast.Attribute):
                        parts = []
                        cur = base
                        while isinstance(cur, ast.Attribute):
                            parts.append(cur.attr)
                            cur = cur.value
                        if isinstance(cur, ast.Name):
                            parts.append(cur.id)
                        parts = list(reversed(parts))
                        dotted = ".".join(parts)
                        results.append(
                            (path, node.lineno, f"attr-usage {dotted}.{symbol}")
                        )
            if len(results) >= max_results:
                break
    except Exception:
        pass
    return results


def find_similar_modules(
    root: Path, target: str, max_results: int = 5, threshold: float = 0.6
) -> List[Tuple[str, float]]:
    similar = []
    for p in root.rglob("*"):
        if p.is_dir() and p.name:
            mod_name = ".".join(p.relative_to(root).parts)
            ratio = difflib.SequenceMatcher(None, mod_name, target).ratio()
            if ratio > threshold:
                similar.append((mod_name, ratio))
        elif p.suffix == ".py" and p.stem:
            parts = list(p.relative_to(root).parts[:-1])  # Convert to list
            mod_name = ".".join(parts + [p.stem])
            ratio = difflib.SequenceMatcher(None, mod_name, target).ratio()
            if ratio > threshold:
                similar.append((mod_name, ratio))
    return sorted(similar, key=lambda x: x[1], reverse=True)[:max_results]


def _format_evidence_item(path: Path, lineno: int, kind: str) -> str:
    try:
        rel = path.relative_to(Path.cwd())
    except Exception:
        rel = path
    return f"{str(rel)}:{lineno}: {kind}"
