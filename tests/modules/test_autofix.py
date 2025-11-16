# tests/modules/test_autofix.py


from importdoc.modules.autofix import FixGenerator


def test_generate_missing_import_fix():
    fix = FixGenerator.generate_missing_import_fix(
        "old_module", "my_symbol", "new_module"
    )
    assert fix.issue_type == "missing_import"
    assert fix.module_name == "old_module"
    assert fix.confidence == 0.85
    assert "Replace incorrect import path" in fix.description
    assert "from old_module import my_symbol" in fix.patch
    assert "from new_module import my_symbol" in fix.patch


def test_generate_circular_import_fix():
    fix = FixGenerator.generate_circular_import_fix(["a", "b", "a"])
    assert fix.issue_type == "circular_import"
    assert fix.module_name == "a -> b -> a"
    assert fix.confidence == 0.70
    assert "Circular import detected" in fix.description
    assert fix.patch is None


def test_generate_missing_dependency_fix():
    fix = FixGenerator.generate_missing_dependency_fix("my_package", "my-package")
    assert fix.issue_type == "missing_dependency"
    assert fix.module_name == "my_package"
    assert fix.confidence == 0.95
    assert "Missing external dependency" in fix.description
    assert fix.patch is None
    assert any("pip install my-package" in s for s in fix.manual_steps)
