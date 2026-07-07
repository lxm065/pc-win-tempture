"""Dump LHM HTTP JSON tree to see real structure."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

with urllib.request.urlopen("http://127.0.0.1:8085/data.json", timeout=3) as r:
    data = json.loads(r.read())

# Walk and print first few levels
def walk(node, depth=0):
    if depth > 5:
        return
    if isinstance(node, list):
        for child in node[:1]:
            walk(child, depth)
        return
    if isinstance(node, dict):
        t = node.get("Type") or node.get("type") or "?"
        text = node.get("Text", "")
        val = node.get("Value", "")
        kids = len(node.get("Children", []) or [])
        print(f"{'  ' * depth}[{t}] {text!r} = {val} (children: {kids})")
        for child in (node.get("Children") or [])[:1]:
            walk(child, depth + 1)

print("Top-level type:", type(data).__name__)
if isinstance(data, dict):
    print("Top-level keys:", list(data.keys()))
    walk(data, 0)
elif isinstance(data, list):
    print("Length:", len(data))
    walk(data[:1], 0)