# tests/modules/test_worker.py


import subprocess
import sys
from unittest.mock import patch

import pytest

from importdoc.modules.worker import import_module_worker


def test_import_module_worker_success():
    result = import_module_worker("os", timeout=5)
    assert result["success"] is True
    assert result["error"] is None
    assert result["tb"] is None


def test_import_module_worker_failure():
    result = import_module_worker("non_existent_module", timeout=5)
    assert result["success"] is False
    assert result["error"] is not None
    assert result["tb"] is not None


def test_import_module_worker_timeout():
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=1)
        result = import_module_worker("os", timeout=1)
        assert result["success"] is False
        assert "Timeout" in result["error"]
        assert "Timeout" in result["tb"]
