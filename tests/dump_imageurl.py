"""Show ImageURL for each node — to see if it can be used for classification."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def walk(node):
    if isinstance(node, list):
        for c in node:
            walk(c)
        return
    if not isinstance(node, dict):
        return
    text = node.get("Text", "")
    img = node.get("ImageURL", "")
    t = node.get("Type", "")
    if img:
        marker = "LEAF" if t else "HW"
        print(f"[{marker}][{t or '-'}] {text!r:50s} image={img}")
    for c in node.get("Children") or []:
        walk(c)


with urllib.request.urlopen("http://127.0.0.1:8085/data.json", timeout=3) as r:
    data = json.loads(r.read())
walk(data)