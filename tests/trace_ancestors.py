"""Trace ancestors for the misclassified sensors."""
import sys
import json
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def walk_with_path(node, path):
    if isinstance(node, list):
        for child in node:
            yield from walk_with_path(child, path)
        return
    if not isinstance(node, dict):
        return
    text = node.get("Text") or ""
    t = node.get("Type") or ""
    new_path = path + [text]
    if t:
        yield (t, text, new_path)
    children = node.get("Children") or []
    for child in children:
        yield from walk_with_path(child, new_path)


with urllib.request.urlopen("http://127.0.0.1:8085/data.json", timeout=3) as r:
    data = json.loads(r.read())


for kind, name, path in walk_with_path(data, []):
    if kind != "Temperature":
        continue
    full = " / ".join(p for p in path if p)
    print(f"[{kind}] {full}")