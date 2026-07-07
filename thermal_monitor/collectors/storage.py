"""Storage (disk) temperature collector.

Sources (tried in order):
  1. psutil.sensors_temperatures() — chips like "nvme", "drivetemp", "scsi".
  2. WMI MSAta_SMARTData / MSStorageDriver_ATAPISmartData — raw SMART, requires
     admin and is fiddly to parse. We try, swallow errors.

Note: SMART temp isn't standardized; the parsed value may be missing for some
SSDs. We never raise; just return what we got.
"""
from __future__ import annotations

import psutil

from ..utils import get_logger
from .base import TempReading

log = get_logger(__name__)


def _wmi_available() -> bool:
    try:
        import wmi  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def _psutil_storage_temps() -> list[TempReading]:
    try:
        sensors = psutil.sensors_temperatures(fahrenheit=False) or {}
    except Exception as exc:
        log.debug("psutil.sensors_temperatures failed: %s", exc)
        return []

    out: list[TempReading] = []
    storage_keys = ("nvme", "drivetemp", "scsi", "ata", "disk")
    for chip, entries in sensors.items():
        chip_l = chip.lower()
        if not any(k in chip_l for k in storage_keys):
            continue
        for ent in entries:
            if ent.current is None:
                continue
            label = ent.label or chip
            out.append(
                TempReading(label=label, category="storage", celsius=float(ent.current), source="psutil")
            )
    return out


def _wmi_storage_temps() -> list[TempReading]:
    if not _wmi_available():
        return []
    # SMART parsing is too brittle to be reliable cross-vendor. Skip unless
    # we explicitly need it later. Keeping the function as a hook for future
    # implementation (e.g. disk SMART via smartmontools).
    return []


def collect() -> tuple[list[TempReading], list[str]]:
    errors: list[str] = []
    temps: list[TempReading] = []
    # 1) LibreHardwareMonitor WMI (preferred; needs LHM running with WMI enabled)
    from . import lhm

    lhm_temps, _ = lhm.collect_temps()
    temps.extend([t for t in lhm_temps if t.category == "storage"])
    # 2) psutil (silent on 7.x)
    if not temps:
        temps.extend(_psutil_storage_temps())
    # 3) WMI SMART (not implemented — see module docstring)
    if not temps:
        temps.extend(_wmi_storage_temps())
    if not temps:
        errors.append(
            "Storage temperature unavailable. To unlock: install LibreHardwareMonitor, "
            "run it as Administrator, and enable 'WMI' in its Options menu."
        )
    return temps, errors
