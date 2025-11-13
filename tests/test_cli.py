import sys
from unittest.mock import patch

import pytest

from importdoc.cli import main
from importdoc.modules.diagnostics import ImportDiagnostic


def test_main_success():
    with patch.object(sys, "argv", ["importdoc", "os"]):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 0


def test_main_internal_error():
    with patch.object(sys, "argv", ["importdoc", "os"]):
        with patch.object(
            ImportDiagnostic, "run_diagnostic", side_effect=Exception("Test error")
        ):
            with pytest.raises(SystemExit) as e:
                main()
            assert e.value.code == 2
