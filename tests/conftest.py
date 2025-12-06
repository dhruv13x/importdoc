
import pytest
import os
import sys

@pytest.fixture(autouse=True)
def mock_non_root_user(monkeypatch):
    """
    Simulate a non-root user (uid=1000) for all tests by default.
    This prevents `ImportDiagnostic` from raising PermissionError during tests
    running in the sandbox (where we are root).

    Individual tests that want to test root behavior can override this
    by mocking `os.geteuid` again or using `monkeypatch.undo()`.
    """
    if hasattr(os, "geteuid"):
        monkeypatch.setattr(os, "geteuid", lambda: 1000)
