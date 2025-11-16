# tests/modules/test_telemetry.py


import json

from importdoc.modules.telemetry import TelemetryCollector


def test_telemetry_collector_disabled():
    collector = TelemetryCollector(enabled=False)
    collector.record("import_success", "os", 10.0)
    assert len(collector.events) == 0


def test_telemetry_collector_record():
    collector = TelemetryCollector(enabled=True)
    collector.record("import_success", "os", 10.0)
    assert len(collector.events) == 1
    event = collector.events[0]
    assert event.event_type == "import_success"
    assert event.module_name == "os"
    assert event.duration_ms == 10.0


def test_telemetry_collector_export_json():
    collector = TelemetryCollector(enabled=True)
    collector.record("import_success", "os", 10.0)
    json_output = collector.export_json()
    data = json.loads(json_output)
    assert len(data) == 1
    assert data[0]["event_type"] == "import_success"
    assert data[0]["module_name"] == "os"
    assert data[0]["duration_ms"] == 10.0


def test_telemetry_collector_get_summary():
    collector = TelemetryCollector(enabled=True)
    collector.record("import_success", "os", 10.0)
    collector.record("import_failure", "non_existent_module", 20.0)
    summary = collector.get_summary()
    assert summary["total_events"] == 2
    assert summary["by_type"]["import_success"] == 1
    assert summary["by_type"]["import_failure"] == 1
    assert summary["avg_import_time_ms"] == 15.0
    assert len(summary["slowest_imports"]) == 1
    assert summary["slowest_imports"][0]["module"] == "os"
    assert summary["slowest_imports"][0]["duration_ms"] == 10.0
