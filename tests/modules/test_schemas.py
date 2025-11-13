import unittest
from importdoc.modules.schemas import validate_json, JSON_SUMMARY_SCHEMA, FIXES_SCHEMA

class TestSchemas(unittest.TestCase):
    def test_validate_json_summary_schema(self):
        # A valid summary object
        valid_summary = {
            "version": "1.0.0",
            "package": "my_package",
            "discovered_modules": ["mod1", "mod2"],
            "discovery_errors": [],
            "imported_modules": ["mod1"],
            "failed_modules": [],
            "skipped_modules": [],
            "timings": {},
            "module_tree": {},
            "env_info": {},
            "elapsed_seconds": 1.23,
            "auto_fixes": [],
            "telemetry": None,
            "health_check": {"passed": True},
        }
        self.assertTrue(validate_json(valid_summary, JSON_SUMMARY_SCHEMA))

    def test_validate_json_fixes_schema(self):
        # A valid fixes object
        valid_fixes = [
            {
                "issue_type": "missing_import",
                "module_name": "my_module",
                "confidence": 0.85,
                "description": "A description",
                "patch": "a patch",
                "manual_steps": ["step1", "step2"],
            }
        ]
        self.assertTrue(validate_json(valid_fixes, FIXES_SCHEMA))

if __name__ == "__main__":
    unittest.main()
