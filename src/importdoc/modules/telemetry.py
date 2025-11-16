# src/importdoc/modules/telemetry.py

import json
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass
class DiagnosticEvent:
    timestamp: float
    event_type: str
    module_name: str
    duration_ms: float
    metadata: Dict[str, Any]


class TelemetryCollector:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.events: List[DiagnosticEvent] = []
        self._lock = threading.Lock()

    def record(self, event_type: str, module_name: str, duration_ms: float, **metadata):
        if not self.enabled:
            return
        with self._lock:
            self.events.append(
                DiagnosticEvent(
                    timestamp=time.time(),
                    event_type=event_type,
                    module_name=module_name,
                    duration_ms=duration_ms,
                    metadata=metadata,
                )
            )

    def export_json(self) -> str:
        with self._lock:
            return json.dumps([asdict(e) for e in self.events], indent=2)

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self.events)
            by_type = defaultdict(int)
            import_times = []
            for e in self.events:
                by_type[e.event_type] += 1
                if e.event_type in ("import_success", "import_failure"):
                    import_times.append(e.duration_ms)
            avg = (sum(import_times) / len(import_times)) if import_times else 0.0
            slowest = sorted(
                [e for e in self.events if e.event_type == "import_success"],
                key=lambda e: e.duration_ms,
                reverse=True,
            )[:5]
            return {
                "total_events": total,
                "by_type": dict(by_type),
                "avg_import_time_ms": avg,
                "slowest_imports": [
                    {"module": e.module_name, "duration_ms": e.duration_ms}
                    for e in slowest
                ],
            }
