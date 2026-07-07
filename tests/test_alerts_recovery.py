"""Verify AlertNotifier recovery events."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thermal_monitor.alerts.notifier import AlertEvent, AlertNotifier
from thermal_monitor.collectors.base import HardwareSnapshot, TempReading
from thermal_monitor.config import AppConfig
from thermal_monitor.data.repository import Repository


def make_snap(ts: float, celsius):
    return HardwareSnapshot(
        timestamp=ts,
        temps=[TempReading(label="Tdie", category="cpu", celsius=celsius, source="psutil")],
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        cfg = AppConfig()
        cfg.thresholds = {"cpu": 80.0, "gpu": 85.0, "motherboard": 70.0, "storage": 55.0}
        cfg.alert_cooldown_seconds = 0  # disable cooldown for the test

        repo = Repository(Path(td) / "t.db")
        events_log = []
        notifier = AlertNotifier(cfg, repo, on_event=events_log.append)

        # 1. baseline: 50°C -> nothing
        notifier.scan(make_snap(1.0, 50.0))
        assert events_log == [], f"expected no events at 50°C, got {events_log}"

        # 2. climb to 82°C -> warning
        notifier.scan(make_snap(2.0, 82.0))
        assert len(events_log) == 1, f"expected 1 event, got {len(events_log)}"
        assert events_log[-1].level == "warning", events_log[-1]

        # 3. stay at 82°C -> no event (already alerting)
        notifier.scan(make_snap(3.0, 82.0))
        assert len(events_log) == 1, "duplicate warning fired"

        # 4. climb to 95°C -> critical
        notifier.scan(make_snap(4.0, 95.0))
        assert len(events_log) == 2
        assert events_log[-1].level == "critical"

        # 5. drop back to 82°C -> no new event (still in warning/critical zone)
        notifier.scan(make_snap(5.0, 82.0))
        assert len(events_log) == 2, f"got {len(events_log)}: {events_log}"

        # 6. drop to 75°C -> recovered
        notifier.scan(make_snap(6.0, 75.0))
        assert len(events_log) == 3, f"expected recovery event, got {len(events_log)}"
        assert events_log[-1].level == "recovered", events_log[-1]

        # 7. stay at 75°C -> no event
        notifier.scan(make_snap(7.0, 75.0))
        assert len(events_log) == 3, "spurious recovery"

        # 8. climb again to 82°C -> warning (re-alert after recovery)
        notifier.scan(make_snap(8.0, 82.0))
        assert len(events_log) == 4
        assert events_log[-1].level == "warning"

        # 9. drop again to 50°C -> recovered
        notifier.scan(make_snap(9.0, 50.0))
        assert len(events_log) == 5
        assert events_log[-1].level == "recovered"

        # Verify the recovered events have sensible values
        recovered = [e for e in events_log if e.level == "recovered"]
        assert len(recovered) == 2
        assert all(e.threshold == 80.0 for e in recovered)

        print(f"OK: {len(events_log)} events in correct sequence")
        print("  warning -> critical -> recovered -> warning -> recovered")
        for e in events_log:
            print(f"  {e.level:10s} {e.label}: {e.value:.1f}°C (>{e.threshold:.0f})")

        repo.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())