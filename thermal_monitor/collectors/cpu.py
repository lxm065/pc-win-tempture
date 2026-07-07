"""CPU temperature + usage collector.

Sources (tried in order, first non-empty wins):
  1. psutil.sensors_temperatures() — works when LibreHardwareMonitor / HWiNFO
     shared-memory driver is installed; on bare Windows returns {}.
  2. WMI Win32_TemperatureProbe / MSAcpi_ThermalZoneTemperature — most bare
     Windows systems return no data here, but we still try.

Usage: psutil.cpu_percent(percpu=True) for per-core + total.
"""
from __future__ import annotations

import psutil

from ..utils import get_logger
from .base import HardwareSnapshot, TempReading, UsageReading

log = get_logger(__name__)


def _psutil_cpu_temps() -> list[TempReading]:
    """Read CPU temps via psutil (LHM/HWiNFO backend)."""
    out: list[TempReading] = []
    try:
        sensors = psutil.sensors_temperatures(fahrenheit=False) or {}
    except Exception as exc:
        log.debug("psutil.sensors_temperatures failed: %s", exc)
        return out

    if not sensors:
        return out

    # Common chip names: coretemp, k10temp, zenpower, cpu_thermal
    cpu_chip_keys = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "cpu-thermal", "acpitz")
    for chip, entries in sensors.items():
        chip_l = chip.lower()
        if not any(k in chip_l for k in cpu_chip_keys):
            continue
        for ent in entries:
            label = ent.label or chip
            if ent.current is None:
                continue
            out.append(
                TempReading(
                    label=label if label.lower() != chip.lower() else f"CPU {label}",
                    category="cpu",
                    celsius=float(ent.current),
                    source="psutil",
                )
            )
    return out


def _wmi_cpu_temp() -> list[TempReading]:
    """Last-resort: WMI thermal probes (usually empty on consumer hardware)."""
    if not _wmi_available():
        return []
    try:
        import wmi  # type: ignore

        c = wmi.WMI(namespace="root\\wmi")
        out: list[TempReading] = []

        # MSAcpi_ThermalZoneTemperature — returns Kelvin*10
        try:
            for tz in c.MSAcpi_ThermalZoneTemperature():
                # CurrentTemperature is in 0.1 Kelvin; convert to Celsius
                kelvin_x10 = getattr(tz, "CurrentTemperature", None)
                if kelvin_x10 is None:
                    continue
                celsius = (kelvin_x10 / 10.0) - 273.15
                if -50 < celsius < 150:
                    out.append(
                        TempReading(
                            label=getattr(tz, "InstanceName", "Thermal Zone") or "Thermal Zone",
                            category="cpu",
                            celsius=round(celsius, 1),
                            source="wmi",
                        )
                    )
        except Exception as exc:
            log.debug("MSAcpi_ThermalZoneTemperature failed: %s", exc)

        return out
    except Exception as exc:
        log.debug("WMI CPU temp collection failed: %s", exc)
        return []


def _wmi_available() -> bool:
    try:
        import wmi  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def _lhm_cpu_temps() -> list[TempReading]:
    from . import lhm

    all_temps, _ = lhm.collect_temps()
    return [t for t in all_temps if t.category == "cpu"]


def collect() -> tuple[list[TempReading], list[UsageReading], list[str]]:
    errors: list[str] = []
    temps: list[TempReading] = []

    # 1) LibreHardwareMonitor WMI (most accurate; needs LHM running with WMI enabled)
    temps.extend(_lhm_cpu_temps())
    # 2) psutil sensors (only works on psutil 6.x; silently empty on 7.x)
    if not temps:
        temps.extend(_psutil_cpu_temps())
    # 3) WMI thermal zones (last-resort fallback; usually empty on consumer hardware)
    if not temps:
        temps.extend(_wmi_cpu_temp())

    # Usage — psutil always works
    usages: list[UsageReading] = []
    try:
        per = psutil.cpu_percent(interval=None, percpu=True)
        for idx, p in enumerate(per):
            usages.append(
                UsageReading(label=f"CPU Core {idx}", percent=float(p), source="psutil")
            )
        if per:
            usages.append(
                UsageReading(label="CPU Total", percent=float(sum(per) / len(per)), source="psutil")
            )
    except Exception as exc:
        errors.append(f"cpu_percent failed: {exc}")

    if not temps:
        errors.append(
            "CPU temperature unavailable. To unlock: install LibreHardwareMonitor, "
            "run it as Administrator, and enable 'WMI' in its Options menu."
        )

    return temps, usages, errors
