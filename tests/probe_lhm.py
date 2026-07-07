"""Probe LHM via WMI namespace and HTTP. Prints what's reachable."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 1. WMI
print("=" * 60)
print(" 1. WMI probe")
print("=" * 60)
try:
    import wmi
    for ns in [r"root\LibreHardwareMonitor", r"root\LHM"]:
        try:
            c = wmi.WMI(namespace=ns)
            sensors = list(c.Sensor())
            print(f"  {ns}: OK — {len(sensors)} sensors total")
            for s in sensors[:10]:
                print(f"    [{getattr(s, 'SensorType', '?')}] {getattr(s, 'Name', '?')} = {getattr(s, 'Value', '?')}")
        except Exception as exc:
            print(f"  {ns}: FAIL — {exc}")
except ImportError:
    print("  wmi module not installed")

# 2. HTTP
print()
print("=" * 60)
print(" 2. HTTP probe (default localhost:8085)")
print("=" * 60)
for path in ["/", "/data.json", "/sensor", "/api/sensors"]:
    url = f"http://localhost:8085{path}"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            body = r.read()
            print(f"  {path}: HTTP {r.status}, {len(body)} bytes")
            if path == "/data.json" and r.headers.get("Content-Type", "").startswith("application/json"):
                j = json.loads(body)
                print(f"    JSON keys: {list(j.keys()) if isinstance(j, dict) else 'list'}")
    except Exception as exc:
        print(f"  {path}: {type(exc).__name__}: {exc}")