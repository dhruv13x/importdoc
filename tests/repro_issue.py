
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from importdoc.modules.analysis import ErrorAnalyzer
from importdoc.modules.config import DiagnosticConfig

class TestAnalysisRepro:
    def test_too_many_suggestions_repro(self, tmp_path):
        """
        Simulate a scenario where a symbol is defined in MANY files.
        Verify that the analyzer currently produces too many suggestions.
        """
        # Setup a fake project structure
        project_root = tmp_path / "myproject"
        project_root.mkdir()
        (project_root / "src").mkdir()
        (project_root / "src" / "__init__.py").touch()
        (project_root / "src" / "main.py").write_text("from .utils import CommonSymbol")
        (project_root / "src" / "utils.py").write_text("# empty") # Symbol missing here

        # Create many files that define 'CommonSymbol'
        for i in range(20):
            p = project_root / "src" / f"module_{i}.py"
            p.write_text(f"class CommonSymbol:\n    pass")
        
        # Add project_root to sys.path so resolution works
        sys.path.insert(0, str(project_root))
        try:
            # Setup Analyzer
            config = DiagnosticConfig(allow_root=True)
            analyzer = ErrorAnalyzer(config)
            
            error = ImportError("cannot import name 'CommonSymbol' from 'myproject.src.utils'")
            
            # Run analysis
            context = analyzer.analyze(
                module_name="myproject.src.main",
                error=error,
                tb_str=None,
                project_root=project_root,
                current_package="myproject",
                import_stack=[]
            )
            
            # count "Possible correct import" suggestions
            import_suggestions = [s for s in context["suggestions"] if "Possible correct import" in s]
            
            print(f"\nFound {len(import_suggestions)} import suggestions.")
            print(f"Total suggestions: {len(context['suggestions'])}")
            
            # Assert that we have LIMITED the suggestions
            # We expect max 3 specific import suggestions
            assert len(import_suggestions) <= 3
            # And total suggestions should be capped at 5
            assert len(context["suggestions"]) <= 5
            # But we should still have found at least one
            assert len(import_suggestions) > 0
        finally:
            sys.path.pop(0)
