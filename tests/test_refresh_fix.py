"""Smoke test for refresh fix — runs collect_snapshot twice to verify no deadlock."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thermal_monitor.collectors.aggregator import collect_snapshot

snap1 = collect_snapshot()
print(f"Run 1: {len(snap1.temps)} temps, {len(snap1.fans)} fans, {len(snap1.usages)} usages, {len(snap1.errors)} errors")

snap2 = collect_snapshot()
print(f"Run 2: {len(snap2.temps)} temps, {len(snap2.fans)} fans, {len(snap2.usages)} usages, {len(snap2.errors)} errors")

print("OK - no deadlock")