"""Smoke test: run the collectors once and dump what we got.

Useful to verify hardware support without launching the full UI:
    python -m tests.test_collectors
or
    start.bat --smoke
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# allow running as `python tests/test_collectors.py` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thermal_monitor.collectors.aggregator import collect_snapshot
from thermal_monitor.collectors import cpu, gpu, motherboard, storage


def main() -> int:
    print("=" * 60)
    print(" PC Temperature Monitor - smoke test")
    print("=" * 60)

    snap = collect_snapshot()
    print(f"\nCollected at {time.strftime('%H:%M:%S', time.localtime(snap.timestamp))}")
    print(f"Errors: {len(snap.errors)}")
    for e in snap.errors:
        print(f"  - {e}")

    print(f"\nTemperatures ({len(snap.temps)} sensors):")
    for t in snap.temps:
        c = f"{t.celsius:.1f} C" if t.celsius is not None else "N/A"
        print(f"  [{t.category:12s}] {t.label:40s} {c:>10s}   (src: {t.source})")

    print(f"\nFans ({len(snap.fans)} sensors):")
    for f in snap.fans:
        rpm = f"{f.rpm} RPM" if f.rpm is not None else "N/A"
        print(f"  {f.label:40s} {rpm:>12s}   (src: {f.source})")

    print(f"\nUsage ({len(snap.usages)} entries):")
    for u in snap.usages:
        p = f"{u.percent:.1f}%" if u.percent is not None else "N/A"
        print(f"  {u.label:40s} {p:>10s}   (src: {u.source})")

    print(f"\nMemory: {snap.mem_percent:.1f}%" if snap.mem_percent is not None else "\nMemory: N/A")

    # Sanity assertions
    avail_temps = [t for t in snap.temps if t.celsius is not None]
    if not avail_temps:
        print("\n[WARN] No temperature sensors returned a value.")
        print("       This usually means:")
        print("       - WMI/ACPI on this machine does not expose thermal zones (common on laptops with proprietary EC firmware).")
        print("       - LibreHardwareMonitor is not installed. Install from https://github.com/LibreHardwareMonitor/LibreHardwareMonitor")
        print("         and the shared memory sensor will start returning data via psutil.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
