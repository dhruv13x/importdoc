import unittest
from importdoc.modules.telemetry import TelemetryCollector

class TestTelemetry(unittest.TestCase):
    def test_telemetry_collector(self):
        collector = TelemetryCollector(enabled=True)
        collector.record("test_event", "test_module", 123.45)
        self.assertEqual(len(collector.events), 1)
        self.assertEqual(collector.events[0].event_type, "test_event")
        self.assertEqual(collector.events[0].module_name, "test_module")
        self.assertEqual(collector.events[0].duration_ms, 123.45)

        summary = collector.get_summary()
        self.assertEqual(summary["total_events"], 1)
        self.assertEqual(summary["by_type"]["test_event"], 1)

if __name__ == "__main__":
    unittest.main()
