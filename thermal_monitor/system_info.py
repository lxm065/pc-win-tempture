"""Static-ish system hardware info (collected once at startup + on demand).

Data sources:
  - ``platform`` stdlib: OS / Python / arch / hostname
  - ``psutil``: CPU cores / freq, memory, disks, NICs
  - WMI ``Win32_*``: CPU name, motherboard, GPU name + VRAM

Heavy calls (WMI) are wrapped in try/except so a missing sensor never
crashes the info panel — it just shows "N/A".
"""
from __future__ import annotations

import platform
from typing import Any

import psutil

from .utils import get_logger

log = get_logger(__name__)


# ---- WMI helpers --------------------------------------------------------


def _wmi_first(query: str, prop: str) -> Any:
    try:
        import wmi  # type: ignore

        c = wmi.WMI()
        results = c.query(query)
        if results:
            return getattr(results[0], prop, None)
    except Exception as exc:
        log.debug("wmi %s.%s failed: %s", query, prop, exc)
    return None


def _wmi_all(query: str) -> list:
    try:
        import wmi  # type: ignore

        c = wmi.WMI()
        return list(c.query(query))
    except Exception as exc:
        log.debug("wmi %s failed: %s", query, exc)
    return []


# ---- collector ---------------------------------------------------------


def _fmt_bytes(n: int) -> str:
    if n is None:
        return "N/A"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n //= 1024
    return f"{n} TB"


def _fmt_mhz(m: Any) -> str:
    if m is None or m <= 0:
        return "N/A"
    if m >= 1000:
        return f"{m / 1000:.2f} GHz"
    return f"{int(m)} MHz"


def collect_system_info() -> dict:
    """Return a snapshot of PC hardware info. Never raises."""
    info: dict = {}

    # OS
    info["os"] = platform.platform()
    info["os_release"] = platform.release()
    info["os_version"] = platform.version()
    info["hostname"] = platform.node()
    info["python"] = platform.python_version()
    info["arch"] = platform.machine()
    info["user"] = _wmi_first("SELECT UserName FROM Win32_ComputerSystem", "UserName") or ""

    # CPU
    info["cpu_name"] = (
        _wmi_first("SELECT Name FROM Win32_Processor", "Name")
        or platform.processor()
        or "N/A"
    )
    info["cpu_cores_physical"] = psutil.cpu_count(logical=False) or 0
    info["cpu_cores_logical"] = psutil.cpu_count(logical=True) or 0
    freq = psutil.cpu_freq()
    info["cpu_freq_current"] = freq.current if freq else None
    info["cpu_freq_max"] = freq.max if freq else None
    info["cpu_freq_min"] = freq.min if freq else None
    info["cpu_l2_cache_kb"] = _wmi_first("SELECT L2CacheSize FROM Win32_Processor", "L2CacheSize")
    info["cpu_l3_cache_kb"] = _wmi_first("SELECT L3CacheSize FROM Win32_Processor", "L3CacheSize")

    # Motherboard
    info["motherboard_vendor"] = _wmi_first(
        "SELECT Manufacturer FROM Win32_BaseBoard", "Manufacturer"
    ) or "N/A"
    info["motherboard_product"] = _wmi_first(
        "SELECT Product FROM Win32_BaseBoard", "Product"
    ) or "N/A"
    info["motherboard_serial"] = _wmi_first(
        "SELECT SerialNumber FROM Win32_BaseBoard", "SerialNumber"
    ) or ""
    info["bios_vendor"] = _wmi_first(
        "SELECT Manufacturer FROM Win32_BIOS", "Manufacturer"
    ) or "N/A"
    info["bios_version"] = _wmi_first(
        "SELECT SMBIOSBIOSVersion FROM Win32_BIOS", "SMBIOSBIOSVersion"
    ) or "N/A"
    info["bios_date"] = _wmi_first(
        "SELECT ReleaseDate FROM Win32_BIOS", "ReleaseDate"
    ) or ""

    # GPU
    gpus: list[dict] = []
    for g in _wmi_all("SELECT Name, AdapterRAM, DriverVersion FROM Win32_VideoController"):
        gpus.append(
            {
                "name": g.Name or "N/A",
                "vram_bytes": int(g.AdapterRAM) if g.AdapterRAM else 0,
                "driver": getattr(g, "DriverVersion", "") or "",
            }
        )
    info["gpus"] = gpus

    # Memory
    vm = psutil.virtual_memory()
    info["memory_total_bytes"] = vm.total
    info["memory_speed_mhz"] = _wmi_first(
        "SELECT Speed FROM Win32_PhysicalMemory", "Speed"
    )

    # Disks
    disks: list[dict] = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or not part.mountpoint:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except Exception:
            continue
        # Try to resolve the physical disk model from the device
        model = ""
        try:
            for d in _wmi_all(
                f"SELECT Model FROM Win32_DiskDrive WHERE DeviceID='{part.device.replace('\\\\', '\\\\\\\\')}'"
            ):
                model = d.Model or ""
                break
        except Exception:
            pass
        disks.append(
            {
                "mountpoint": part.mountpoint,
                "device": part.device,
                "fstype": part.fstype,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "model": model,
            }
        )
    info["disks"] = disks

    # Network (active IPv4 NICs only)
    nics: list[dict] = []
    for name, addrs in psutil.net_if_addrs().items():
        # Skip loopback / virtual adapters by checking for IPv4
        v4 = next((a for a in addrs if a.family == psutil.AF_LINK or a.family == 2), None)
        # More reliable: look for AF_INET (family 2)
        ipv4 = next((a for a in addrs if str(a.family) == "AddressFamily.AF_INET" or a.family == 2), None)
        mac = next((a for a in addrs if a.family == psutil.AF_LINK or a.family == -1 or a.family == 17), None)
        if ipv4 is None:
            continue
        # Filter out loopback and APIPA
        if ipv4.address.startswith("127.") or ipv4.address.startswith("169.254."):
            continue
        nics.append(
            {
                "name": name,
                "ip": ipv4.address,
                "mac": mac.address if mac else "",
            }
        )
    info["nics"] = nics

    return info