"""Inspect what _flatten_http_tree actually extracts."""
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thermal_monitor.collectors.lhm import _http_get_json, _flatten_http_tree, DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT

data = _http_get_json(DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT)
flat = []
_flatten_http_tree(data, flat)

print(f"flat entries: {len(flat)}")
types = Counter(e["type"] for e in flat)
print(f"type counts: {dict(types)}")

print()
print("Temperature sensors:")
temps = [e for e in flat if e["type"] == "Temperature"]
for t in temps:
    print(f"  name={t['name']!r} value={t['value']} id={t['identifier']!r}")

print()
print("Fan sensors:")
fans = [e for e in flat if e["type"] == "Fan"]
for f in fans:
    print(f"  name={f['name']!r} value={f['value']} id={f['identifier']!r}")