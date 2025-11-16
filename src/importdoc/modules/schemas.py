# src/importdoc/modules/schemas.py

import os
import logging
from typing import Any, Dict

try:
    import jsonschema
except Exception:
    jsonschema = None

JSON_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "version": {"type": "string"},
        "package": {"type": "string"},
        "discovered_modules": {"type": "array", "items": {"type": "string"}},
        "discovery_errors": {"type": "array", "items": {"type": "object"}},
        "imported_modules": {"type": "array", "items": {"type": "string"}},
        "failed_modules": {"type": "array", "items": {"type": "object"}},
        "skipped_modules": {"type": "array", "items": {"type": "string"}},
        "timings": {"type": "object"},
        "module_tree": {"type": "object"},
        "env_info": {"type": "object"},
        "elapsed_seconds": {"type": "number"},
        "auto_fixes": {"type": "array", "items": {"type": "object"}},
        "telemetry": {"anyOf": [{"type": "object"}, {"type": "null"}]},
        "health_check": {"type": "object"},
    },
    "required": ["version", "package", "health_check"],
}

FIXES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "issue_type": {"type": "string"},
            "module_name": {"type": "string"},
            "confidence": {"type": "number"},
            "description": {"type": "string"},
            "patch": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "manual_steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["issue_type", "module_name", "confidence", "description"],
    },
}


def validate_json(data: Any, schema: Dict) -> bool:
    """Validate JSON if jsonschema installed or environment requests enforcement."""
    enforce = os.environ.get("IMPORT_DIAGNOSTIC_ENFORCE_JSONSCHEMA", "") == "1"
    if jsonschema is None:
        if enforce:
            raise RuntimeError(
                "IMPORT_DIAGNOSTIC_ENFORCE_JSONSCHEMA=1 but 'jsonschema' package is not installed."
            )
        logging.getLogger("import_diagnostic").warning(
            "jsonschema not installed — skipping output validation. Set IMPORT_DIAGNOSTIC_ENFORCE_JSONSCHEMA=1 to require it."
        )
        return True
    try:
        jsonschema.validate(instance=data, schema=schema)
        return True
    except jsonschema.exceptions.ValidationError as e:
        logging.getLogger("import_diagnostic").warning(f"JSON validation failed: {e}")
        if enforce:
            raise
        return False
