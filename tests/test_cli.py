# tests/test_cli.py

import sys
from unittest.mock import patch

import pytest

from importdoc.cli import main
from importdoc.modules.diagnostics import ImportDiagnostic


def test_main_success():
    with patch("importdoc.cli.ImportDiagnostic", autospec=True) as mock_diagnostic_class:
        mock_diagnostic_instance = mock_diagnostic_class.return_value
        with patch.object(sys, "argv", ["importdoc", "os", "--allow-root"]): # Added --allow-root
            with pytest.raises(SystemExit) as e:
                main()
            assert e.value.code == 0
            mock_diagnostic_class.assert_called_once()
            call_kwargs = mock_diagnostic_class.call_args.kwargs
            assert call_kwargs.get("allow_root") is True
            assert call_kwargs.get("continue_on_error") is False
            assert call_kwargs.get("verbose") is False
            assert call_kwargs.get("quiet") is False
            assert call_kwargs.get("use_emojis") is True
            assert call_kwargs.get("log_file") is None
            assert call_kwargs.get("timeout") == 0
            assert call_kwargs.get("dry_run") is False
            assert call_kwargs.get("unload") is False
            assert call_kwargs.get("json_output") is False
            assert call_kwargs.get("parallel") == 0
            assert call_kwargs.get("max_depth") is None
            assert call_kwargs.get("dev_trace") is False
            assert call_kwargs.get("graph") is False
            assert call_kwargs.get("dot_file") is None
            assert call_kwargs.get("show_env") is False
            assert call_kwargs.get("enable_telemetry") is False
            assert call_kwargs.get("enable_cache") is False
            assert call_kwargs.get("generate_fixes") is False
            assert call_kwargs.get("fix_output") is None
            assert call_kwargs.get("safe_mode") is True
            assert call_kwargs.get("safe_skip_imports") is True
            assert call_kwargs.get("max_scan_results") == 200
            assert call_kwargs.get("exclude_patterns") is None
            assert call_kwargs.get("dev_mode") is False

def test_main_internal_error():
    with patch("importdoc.cli.ImportDiagnostic", autospec=True) as mock_diagnostic_class:
        mock_diagnostic_instance = mock_diagnostic_class.return_value
        mock_diagnostic_instance.run_diagnostic.side_effect = Exception("Test error")
        # Mock reporter
        from unittest.mock import MagicMock
        mock_diagnostic_instance.reporter = MagicMock()
        
        with patch.object(sys, "argv", ["importdoc", "os", "--allow-root"]): # Added --allow-root
            with pytest.raises(SystemExit) as e:
                main()
            assert e.value.code == 2
            mock_diagnostic_class.assert_called_once()
            call_kwargs = mock_diagnostic_class.call_args.kwargs
            assert call_kwargs.get("allow_root") is True
            assert call_kwargs.get("continue_on_error") is False
            assert call_kwargs.get("verbose") is False
            assert call_kwargs.get("quiet") is False
            assert call_kwargs.get("use_emojis") is True
            assert call_kwargs.get("log_file") is None
            assert call_kwargs.get("timeout") == 0
            assert call_kwargs.get("dry_run") is False
            assert call_kwargs.get("unload") is False
            assert call_kwargs.get("json_output") is False
            assert call_kwargs.get("parallel") == 0
            assert call_kwargs.get("max_depth") is None
            assert call_kwargs.get("dev_trace") is False
            assert call_kwargs.get("graph") is False
            assert call_kwargs.get("dot_file") is None
            assert call_kwargs.get("show_env") is False
            assert call_kwargs.get("enable_telemetry") is False
            assert call_kwargs.get("enable_cache") is False
            assert call_kwargs.get("generate_fixes") is False
            assert call_kwargs.get("fix_output") is None
            assert call_kwargs.get("safe_mode") is True
            assert call_kwargs.get("safe_skip_imports") is True
            assert call_kwargs.get("max_scan_results") == 200
            assert call_kwargs.get("exclude_patterns") is None
            assert call_kwargs.get("dev_mode") is False
