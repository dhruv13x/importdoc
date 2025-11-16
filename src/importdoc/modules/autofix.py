# src/importdoc/modules/autofix.py

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AutoFix:
    issue_type: str
    module_name: str
    confidence: float
    description: str
    patch: Optional[str]
    manual_steps: List[str]


class FixGenerator:
    @staticmethod
    def generate_missing_import_fix(
        from_module: str, symbol: str, correct_module: str
    ) -> AutoFix:
        original = f"from {from_module} import {symbol}"
        fixed = f"from {correct_module} import {symbol}"
        patch = f"""--- a/module.py
+++ b/module.py
@@ -1,1 +1,1 @@
-{original}
+{fixed}
"""
        return AutoFix(
            issue_type="missing_import",
            module_name=from_module,
            confidence=0.85,
            description=f"Replace incorrect import path '{from_module}' with '{correct_module}'",
            patch=patch,
            manual_steps=[
                f"Update import: {original} → {fixed}",
                "Run tests to verify fix",
                "Check for other occurrences in codebase",
            ],
        )

    @staticmethod
    def generate_circular_import_fix(cycle: List[str]) -> AutoFix:
        return AutoFix(
            issue_type="circular_import",
            module_name=" -> ".join(cycle),
            confidence=0.70,
            description=f"Circular import detected: {' -> '.join(cycle)}",
            patch=None,
            manual_steps=[
                "Move shared code to a separate module",
                "Use lazy imports (import inside function)",
                "Restructure modules to create a DAG",
                "Consider using dependency injection",
            ],
        )

    @staticmethod
    def generate_missing_dependency_fix(package: str, suggested_pip: str) -> AutoFix:
        return AutoFix(
            issue_type="missing_dependency",
            module_name=package,
            confidence=0.95,
            description=f"Missing external dependency: {package}",
            patch=None,
            manual_steps=[
                f"Install package: pip install {suggested_pip}",
                "Add to requirements.txt",
                "Verify version compatibility",
            ],
        )
