"""Motherboard + fan collector.

Sources (tried in order):
  1. psutil.sensors_temperatures() / psutil.sensors_fans() — LHM/HWiNFO backed.
  2. WMI Win32_Fan (rpm), Win32_TemperatureProbe / MSAcpi_ThermalZoneTemperature
     (motherboard temps).

Many desktop boards expose the CPU socket temp under "motherboard" too; we
let that fall through naturally from psutil.
"""
from __future__ import annotations

import psutil

from ..utils import get_logger
from .base import FanReading, TempReading

log = get_logger(__name__)


def _wmi_available() -> bool:
    try:
        import wmi  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def _psutil_mobo_temps() -> list[TempReading]:
    try:
        sensors = psutil.sensors_temperatures(fahrenheit=False) or {}
    except Exception as exc:
        log.debug("psutil.sensors_temperatures failed: %s", exc)
        return []

    out: list[TempReading] = []
    mobo_keys = ("acpitz", "sensors", "mainboard", "motherboard", "nvme", "pch", "amdgpu", "radeon")
    for chip, entries in sensors.items():
        chip_l = chip.lower()
        # Skip anything that looks like CPU/GPU (handled by their own collectors)
        if any(skip in chip_l for skip in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "cpu-thermal")):
            continue
        if "gpu" in chip_l:
            continue
        if not any(k in chip_l for k in mobo_keys):
            # Unknown chip — only include if it has a recognizable label
            for ent in entries:
                if ent.label and any(k in ent.label.lower() for k in ("motherboard", "mainboard", "system", "chipset")):
                    if ent.current is not None:
                        out.append(
                            TempReading(
                                label=ent.label,
                                category="motherboard",
                                celsius=float(ent.current),
                                source="psutil",
                            )
                        )
            continue
        for ent in entries:
            if ent.current is None:
                continue
            label = ent.label or chip
            out.append(
                TempReading(label=label, category="motherboard", celsius=float(ent.current), source="psutil")
            )
    return out


def _wmi_mobo_temp() -> list[TempReading]:
    if not _wmi_available():
        return []
    try:
        import wmi  # type: ignore

        c = wmi.WMI(namespace="root\\wmi")
        out: list[TempReading] = []
        try:
            for tz in c.MSAcpi_ThermalZoneTemperature():
                kelvin_x10 = getattr(tz, "CurrentTemperature", None)
                if kelvin_x10 is None:
                    continue
                celsius = (kelvin_x10 / 10.0) - 273.15
                if -50 < celsius < 150:
                    out.append(
                        TempReading(
                            label=getattr(tz, "InstanceName", "ACPI Zone") or "ACPI Zone",
                            category="motherboard",
                            celsius=round(celsius, 1),
                            source="wmi",
                        )
                    )
        except Exception as exc:
            log.debug("WMI mobo temp failed: %s", exc)
        return out
    except Exception as exc:
        log.debug("WMI mobo collector failed: %s", exc)
        return []


def _psutil_fans() -> list[FanReading]:
    try:
        fans = psutil.sensors_fans() or {}
    except Exception as exc:
        log.debug("psutil.sensors_fans failed: %s", exc)
        return {}
    out: list[FanReading] = []
    for chip, entries in fans.items():
        for ent in entries:
            rpm = int(ent.current) if ent.current is not None else None
            label = ent.label or chip
            out.append(FanReading(label=label, rpm=rpm, source="psutil"))
    return out


def _wmi_fans() -> list[FanReading]:
    if not _wmi_available():
        return []
    try:
        import wmi  # type: ignore

        c = wmi.WMI()
        out: list[FanReading] = []
        try:
            for f in c.Win32_Fan():
                rpm = getattr(f, "DesiredSpeed", None) or getattr(f, "Speed", None)
                if rpm is None:
                    continue
                try:
                    rpm_int = int(rpm)
                except (ValueError, TypeError):
                    continue
                out.append(
                    FanReading(
                        label=getattr(f, "Name", None) or getattr(f, "DeviceID", "Fan") or "Fan",
                        rpm=rpm_int,
                        source="wmi",
                    )
                )
        except Exception as exc:
            log.debug("WMI Win32_Fan failed: %s", exc)
        return out
    except Exception as exc:
        log.debug("WMI fan collector failed: %s", exc)
        return []


def collect() -> tuple[list[TempReading], list[FanReading], list[str]]:
    errors: list[str] = []
    temps: list[TempReading] = []
    fans: list[FanReading] = []

    # 1) LibreHardwareMonitor WMI (best source; requires LHM running with WMI enabled)
    from . import lhm

    lhm_temps, _ = lhm.collect_temps()
    temps.extend([t for t in lhm_temps if t.category == "motherboard"])
    lhm_fans, _ = lhm.collect_fans()
    fans.extend(lhm_fans)
    # 2) psutil sensors (silent on psutil 7.x)
    if not temps:
        temps.extend(_psutil_mobo_temps())
    if not fans:
        fans.extend(_psutil_fans())
    # 3) WMI thermal zones / Win32_Fan (last resort)
    if not temps:
        temps.extend(_wmi_mobo_temp())
    if not fans:
        fans.extend(_wmi_fans())

    if not temps:
        errors.append(
            "Motherboard temperature unavailable. To unlock: install LibreHardwareMonitor, "
            "run it as Administrator, and enable 'WMI' in its Options menu."
        )
    if not fans:
        errors.append(
            "Fan RPM unavailable. To unlock: install LibreHardwareMonitor, "
            "run it as Administrator, and enable 'WMI' in its Options menu."
        )

    return temps, fans, errors
