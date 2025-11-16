# tests/modules/test_schemas.py


import os
from unittest.mock import patch

import pytest

from importdoc.modules.schemas import validate_json

MOCK_SCHEMA = {"type": "object", "properties": {"key": {"type": "string"}}}


def test_validate_json_success():
    assert validate_json({"key": "value"}, MOCK_SCHEMA) is True


def test_validate_json_failure():
    assert validate_json({"key": 123}, MOCK_SCHEMA) is False


@patch.dict(os.environ, {"IMPORT_DIAGNOSTIC_ENFORCE_JSONSCHEMA": "1"})
def test_validate_json_enforced_failure():
    with pytest.raises(Exception):
        validate_json({"key": 123}, MOCK_SCHEMA)


def test_validate_json_no_jsonschema():
    with patch("importdoc.modules.schemas.jsonschema", None):
        assert validate_json({"key": "value"}, MOCK_SCHEMA) is True


@patch.dict(os.environ, {"IMPORT_DIAGNOSTIC_ENFORCE_JSONSCHEMA": "1"})
def test_validate_json_enforced_no_jsonschema():
    with patch("importdoc.modules.schemas.jsonschema", None):
        with pytest.raises(RuntimeError):
            validate_json({"key": "value"}, MOCK_SCHEMA)
