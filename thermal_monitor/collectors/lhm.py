"""LibreHardwareMonitor collector.

Two data paths are tried, in order:

1. **WMI namespace** (preferred): ``root\\LibreHardwareMonitor``. Requires
   the user to enable "WMI" / "Allow remote access" in LHM Options.
2. **HTTP server** (fallback): ``http://localhost:8085`` by default. The
   newer LibreHardwareMonitor .NET 10 builds expose only the web server, not
   WMI — when WMI is missing this path usually works.

In both cases, the LHM process must be running as Administrator (it needs
ring0 access to read CPU/EC temperatures).

Identifier format (from LHM WMI Sensor class):
    /<hardware>/<instance>/<sensor-type>/<index>

We map these prefixes to our internal categories.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from ..utils import get_logger
from .base import FanReading, TempReading

log = get_logger(__name__)

# Try a couple of namespaces — older LHM versions used different names.
WMI_NAMESPACES = [
    r"root\LibreHardwareMonitor",
    r"root\LHM",
]

# Default HTTP server (LHM Options → Remote Web Server → port)
DEFAULT_HTTP_HOST = "localhost"
DEFAULT_HTTP_PORT = 8085


# ---- identifier -> category --------------------------------------------

_PREFIX_TO_CATEGORY: list[tuple[str, str]] = [
    ("/amdcpu/", "cpu"),
    ("/intelcpu/", "cpu"),
    ("/cpu/", "cpu"),
    ("/gpu-nvidia/", "gpu"),
    ("/gpu-amd/", "gpu"),
    ("/gpu-intel/", "gpu"),
    ("/gpu/", "gpu"),
    ("/nvme/", "storage"),
    ("/ata/", "storage"),
    ("/scsi/", "storage"),
    ("/hdd/", "storage"),
    ("/storage/", "storage"),
    ("/samsung/", "storage"),
    ("/mainboard/", "motherboard"),
    ("/motherboard/", "motherboard"),
    ("/acpi/", "motherboard"),
    ("/ram/", "motherboard"),
    ("/intelch", "motherboard"),
]


def _category_for(identifier: str) -> str:
    if not identifier:
        return "motherboard"
    lower = identifier.lower()
    for prefix, cat in _PREFIX_TO_CATEGORY:
        if lower.startswith(prefix):
            return cat
    return "motherboard"


def _label_for(identifier: str, name: str) -> str:
    if name and name.strip():
        return name.strip()
    parts = identifier.strip("/").split("/")
    return parts[-1] if parts else identifier


# ---- WMI path -----------------------------------------------------------


def _wmi_connect():
    """Try each known namespace; return a connected wmi.WMI on success."""
    import wmi  # type: ignore

    last_err: Optional[Exception] = None
    for ns in WMI_NAMESPACES:
        try:
            c = wmi.WMI(namespace=ns)
            # Touch Sensor to confirm it's reachable
            _ = list(c.Sensor())[:1]
            return c
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"WMI namespace unavailable: {last_err}")


def _collect_temps_wmi(c) -> tuple[list[TempReading], list[str]]:
    errors: list[str] = []
    out: list[TempReading] = []
    try:
        for s in c.Sensor():
            try:
                if getattr(s, "SensorType", "") != "Temperature":
                    continue
                value = getattr(s, "Value", None)
                if value is None:
                    continue
                celsius = float(value)
                if celsius <= 0 or celsius > 150:
                    continue
                identifier = getattr(s, "Identifier", "") or ""
                name = getattr(s, "Name", "") or ""
                out.append(
                    TempReading(
                        label=_label_for(identifier, name),
                        category=_category_for(identifier),
                        celsius=round(celsius, 1),
                        source="lhm-wmi",
                    )
                )
            except Exception as exc:
                log.debug("WMI temp sensor skipped: %s", exc)
    except Exception as exc:
        errors.append(f"LHM WMI query failed: {exc}")
    return out, errors


def _collect_fans_wmi(c) -> tuple[list[FanReading], list[str]]:
    errors: list[str] = []
    out: list[FanReading] = []
    try:
        for s in c.Sensor():
            try:
                if getattr(s, "SensorType", "") != "Fan":
                    continue
                value = getattr(s, "Value", None)
                if value is None:
                    continue
                rpm = int(float(value))
                if rpm <= 0:
                    continue
                identifier = getattr(s, "Identifier", "") or ""
                name = getattr(s, "Name", "") or ""
                out.append(
                    FanReading(
                        label=_label_for(identifier, name),
                        rpm=rpm,
                        source="lhm-wmi",
                    )
                )
            except Exception as exc:
                log.debug("WMI fan sensor skipped: %s", exc)
    except Exception as exc:
        errors.append(f"LHM WMI query failed: {exc}")
    return out, errors


# ---- value parsing ------------------------------------------------------


_VALUE_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


def _to_float(v: Any) -> Optional[float]:
    """LHM Value fields come as strings like "45.5 °C" or "1135 RPM" — strip
    the unit and parse the leading number. Returns None if unparseable."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = _VALUE_NUM.search(str(v))
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


# ---- HTTP path ----------------------------------------------------------


def _http_alive(host: str = DEFAULT_HTTP_HOST, port: int = DEFAULT_HTTP_PORT, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def _http_get_json(host: str, port: int, timeout: float = 2.0) -> Optional[Any]:
    """Try a handful of known LHM HTTP API paths and return the parsed JSON."""
    paths = ["/data.json", "/sensor", "/api/sensors", "/api/data", "/", "/data"]
    last_err: Optional[Exception] = None
    for path in paths:
        try:
            req = urllib.request.Request(
                f"http://{host}:{port}{path}",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status != 200:
                    continue
                body = r.read().decode("utf-8", errors="replace")
                try:
                    return json.loads(body)
                except json.JSONDecodeError as exc:
                    last_err = exc
                    continue
        except (urllib.error.URLError, OSError) as exc:
            last_err = exc
            continue
    log.debug("HTTP probe failed: %s", last_err)
    return None


def _flatten_http_tree(node: Any, out: list[dict], current_category: str = "motherboard") -> None:
    """LHM's tree-shaped JSON: recursively walk children collecting sensor dicts.

    The HTTP JSON doesn't carry a path-style identifier (id is just a sequence
    number), so we propagate hardware category down the tree based on the
    Text of ancestor hardware nodes — "AMD Ryzen ..." => cpu, "NVIDIA
    GeForce ..." => gpu, "Samsung SSD ..." => storage, etc.
    """
    if isinstance(node, list):
        for child in node:
            _flatten_http_tree(child, out, current_category)
        return
    if not isinstance(node, dict):
        return

    text = (node.get("Text") or node.get("text") or "").lower()
    image = (node.get("ImageURL") or node.get("imageurl") or "").lower()
    new_category = current_category

    # Prefer ImageURL — LHM ships a per-hardware icon (mainboard.png,
    # cpu.png, gpu.png, hdd.png, ram.png, chip.png). This is more reliable
    # than parsing vendor names which can be wildcards (Seagate "ST...",
    # Samsung "SAMSUNG SSD...").
    image_to_category = {
        "cpu.png": "cpu",
        "gpu.png": "gpu",
        "hdd.png": "storage",
        "mainboard.png": "motherboard",
        "chip.png": "motherboard",
        "ram.png": "motherboard",
    }
    for icon_name, cat in image_to_category.items():
        if image.endswith(icon_name):
            new_category = cat
            break
    else:
        # Fallback to text-keyword matching when ImageURL is absent (older LHM).
        for keywords, cat in (
            (("ryzen", "core i", "core™", "threadripper", "xeon", "epyc", "pentium", "celeron"), "cpu"),
            (("nvidia", "geforce", "radeon", "rtx", "gtx", "rx ", "arc "), "gpu"),
            (
                (
                    "nvme", " ssd", " hdd", "samsung ", "wd black", "wd blue",
                    "wd red", "wd gold", "crucial", "kingston", "seagate",
                    "toshiba", "fanxiang", "adata", "patriot", "gigabyte ssd",
                    "980 ", "970 ", "960 ", "860 ", "850 ", "pm83", "pm9a",
                    "mp600", "firecuda", "barron", "rocket ",
                ),
                "storage",
            ),
        ):
            if any(k in text for k in keywords):
                new_category = cat
                break

    t = node.get("Type") or node.get("type") or ""
    if t in ("Temperature", "Fan", "Load", "Clock", "Power", "Voltage", "Data", "Control"):
        out.append(
            {
                "type": t,
                "name": node.get("Text") or node.get("text") or node.get("Name") or "",
                "value": node.get("Value") if "Value" in node else node.get("value"),
                "min": node.get("Min"),
                "max": node.get("Max"),
                "identifier": (
                    node.get("Identifier")
                    or node.get("identifier")
                    or node.get("Id")
                    or node.get("id")
                    or ""
                ),
                "category": new_category,
            }
        )
    children = node.get("Children") or node.get("children")
    if children:
        _flatten_http_tree(children, out, new_category)


def _collect_temps_http(host: str = DEFAULT_HTTP_HOST, port: int = DEFAULT_HTTP_PORT) -> tuple[list[TempReading], list[str]]:
    data = _http_get_json(host, port)
    if data is None:
        return [], [f"LHM HTTP server unreachable on {host}:{port}"]
    flat: list[dict] = []
    _flatten_http_tree(data, flat)
    out: list[TempReading] = []
    for s in flat:
        if s["type"] != "Temperature":
            continue
        name_lower = (s["name"] or "").lower()
        # SMART threshold fields (Warning/Critical Temperature) are static
        # values, not live readings — skip them.
        if "warning" in name_lower or "critical" in name_lower:
            continue
        celsius = _to_float(s["value"])
        if celsius is None:
            continue
        if celsius <= 0 or celsius > 150:
            continue
        identifier = str(s["identifier"]) if s["identifier"] else ""
        out.append(
            TempReading(
                label=_label_for(identifier, s["name"]),
                category=s.get("category", "motherboard"),
                celsius=round(celsius, 1),
                source="lhm-http",
            )
        )
    return out, []


def _collect_fans_http(host: str = DEFAULT_HTTP_HOST, port: int = DEFAULT_HTTP_PORT) -> tuple[list[FanReading], list[str]]:
    data = _http_get_json(host, port)
    if data is None:
        return [], [f"LHM HTTP server unreachable on {host}:{port}"]
    flat: list[dict] = []
    _flatten_http_tree(data, flat)
    out: list[FanReading] = []
    for s in flat:
        if s["type"] != "Fan":
            continue
        rpm_v = _to_float(s["value"])
        if rpm_v is None:
            continue
        rpm = int(rpm_v)
        if rpm <= 0:
            continue
        identifier = str(s["identifier"]) if s["identifier"] else ""
        out.append(
            FanReading(
                label=_label_for(identifier, s["name"]),
                rpm=rpm,
                source="lhm-http",
            )
        )
    return out, []


# ---- unified API --------------------------------------------------------


def status() -> str:
    """Return 'wmi', 'http', or 'none' for UI display."""
    try:
        _wmi_connect()
        return "wmi"
    except Exception:
        pass
    if _http_alive():
        return "http"
    return "none"


def collect_temps() -> tuple[list[TempReading], list[str]]:
    """Read all Temperature sensors from LHM (WMI first, then HTTP). Never raises."""
    try:
        c = _wmi_connect()
        temps, errs = _collect_temps_wmi(c)
        if temps:
            return temps, errs
    except Exception as exc:
        log.debug("WMI connect failed: %s", exc)
    # HTTP fallback
    return _collect_temps_http()


def collect_fans() -> tuple[list[FanReading], list[str]]:
    """Read all Fan sensors from LHM (WMI first, then HTTP). Never raises."""
    try:
        c = _wmi_connect()
        fans, errs = _collect_fans_wmi(c)
        if fans:
            return fans, errs
    except Exception as exc:
        log.debug("WMI connect failed: %s", exc)
    return _collect_fans_http()