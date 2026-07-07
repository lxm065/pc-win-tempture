"""Aggregate all collectors and produce a unified HardwareSnapshot.

Polled on a QTimer in the main thread (or a worker thread — see app.py).
"""
from __future__ import annotations

import time

import psutil

from ..utils import get_logger
from .base import HardwareSnapshot
from . import cpu, gpu, motherboard, storage

log = get_logger(__name__)


def collect_snapshot() -> HardwareSnapshot:
    """Run every collector once and merge into one snapshot. Never raises."""
    snap = HardwareSnapshot(timestamp=time.time())
    try:
        c_temps, c_usages, c_errs = cpu.collect()
        snap.temps.extend(c_temps)
        snap.usages.extend(c_usages)
        snap.errors.extend(c_errs)
    except Exception as exc:
        snap.errors.append(f"cpu collector crashed: {exc}")

    try:
        g_temps, g_usages, g_errs = gpu.collect()
        snap.temps.extend(g_temps)
        snap.usages.extend(g_usages)
        snap.errors.extend(g_errs)
    except Exception as exc:
        snap.errors.append(f"gpu collector crashed: {exc}")

    try:
        m_temps, m_fans, m_errs = motherboard.collect()
        snap.temps.extend(m_temps)
        snap.fans.extend(m_fans)
        snap.errors.extend(m_errs)
    except Exception as exc:
        snap.errors.append(f"motherboard collector crashed: {exc}")

    try:
        s_temps, s_errs = storage.collect()
        snap.temps.extend(s_temps)
        snap.errors.extend(s_errs)
    except Exception as exc:
        snap.errors.append(f"storage collector crashed: {exc}")

    try:
        snap.mem_percent = float(psutil.virtual_memory().percent)
    except Exception as exc:
        snap.errors.append(f"virtual_memory failed: {exc}")

    return snap
