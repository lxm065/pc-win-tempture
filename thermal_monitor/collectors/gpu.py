"""GPU collector.

Strategy:
  - Detect NVIDIA via `nvidia-smi` on PATH (or C:\\Windows\\System32).
  - If found: query temp / util / mem with `nvidia-smi --query-gpu=...`.
  - Fallback: WMI Win32_VideoController (gives name but no temp/util — still
    surface the name so UI can show "GPU: GeForce RTX 4070 (no sensor)").

Multi-GPU is supported: nvidia-smi returns one line per GPU.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from ..utils import get_logger
from .base import TempReading, UsageReading

log = get_logger(__name__)

# Some Windows machines have nvidia-smi in System32 even without a working
# driver (residual install). Check both PATH and the well-known path.
_NVIDIA_SMI_CANDIDATES = [
    shutil.which("nvidia-smi"),
    r"C:\Windows\System32\nvidia-smi.exe",
    r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
]


def _find_nvidia_smi() -> Optional[str]:
    for p in _NVIDIA_SMI_CANDIDATES:
        if p and shutil.os.path.isfile(p):
            return p
    return None


def _query_nvidia_smi() -> list[tuple[TempReading, UsageReading, str, float]]:
    """Run nvidia-smi once and parse multi-GPU output. Returns (temp, usage, name, mem_used_mb)."""
    exe = _find_nvidia_smi()
    if not exe:
        return []

    cmd = [
        exe,
        "--query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log.debug("nvidia-smi exec failed: %s", exc)
        return []

    if proc.returncode != 0 or not proc.stdout.strip():
        log.debug("nvidia-smi no output: rc=%s stderr=%s", proc.returncode, proc.stderr[:200])
        return []

    out: list[tuple[TempReading, UsageReading, str, float]] = []
    for line in proc.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            idx = int(parts[0])
            name = parts[1]
            temp_c = float(parts[2]) if parts[2] not in ("", "[Not Supported]") else None
            util = float(parts[3]) if parts[3] not in ("", "[Not Supported]") else None
            mem_used_mb = float(parts[4]) if parts[4] not in ("", "[Not Supported]") else 0.0
        except ValueError as exc:
            log.debug("nvidia-smi parse error on line %r: %s", line, exc)
            continue

        temp = TempReading(
            label=f"GPU {idx} {name}",
            category="gpu",
            celsius=temp_c,
            source="nvidia-smi",
        )
        usage = UsageReading(
            label=f"GPU {idx} {name}",
            percent=util,
            source="nvidia-smi",
        )
        out.append((temp, usage, name, mem_used_mb))

    return out


def _wmi_gpu_names() -> list[str]:
    """Fallback: just give us GPU names so the UI can list them as N/A temp."""
    try:
        import wmi  # type: ignore

        c = wmi.WMI()
        return [vc.Name for vc in c.Win32_VideoController() if vc.Name]
    except Exception as exc:
        log.debug("WMI Win32_VideoController failed: %s", exc)
        return []


def collect() -> tuple[list[TempReading], list[UsageReading], list[str]]:
    errors: list[str] = []
    temps: list[TempReading] = []
    usages: list[UsageReading] = []

    nv = _query_nvidia_smi()
    if nv:
        for temp, usage, _name, _mem in nv:
            temps.append(temp)
            usages.append(usage)
        return temps, usages, errors

    # Fallback: name only
    names = _wmi_gpu_names()
    if names:
        for idx, name in enumerate(names):
            temps.append(
                TempReading(label=f"GPU {idx} {name}", category="gpu", celsius=None, source="wmi")
            )
        errors.append("GPU temperature requires nvidia-smi (NVIDIA) or LibreHardwareMonitor (AMD/Intel)")
    else:
        errors.append("No GPU detected")

    return temps, usages, errors
