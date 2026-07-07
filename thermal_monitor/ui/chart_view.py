"""Real-time chart — one curve per hardware category, showing the hottest
sensor in that category at each sample.

User-facing simplification: rather than dumping every CPU core / every
motherboard probe into the chart (16+ lines, unreadable), we render exactly
four lines — CPU / GPU / Motherboard / Storage — each tracking the maximum
celsius across its category at every poll.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..collectors.base import HardwareSnapshot
from ..config import AppConfig

pg.setConfigOption("background", "#0d1117")
pg.setConfigOption("foreground", "#c9d1d9")

# The four canonical categories, in display order.
_CATEGORIES: list[tuple[str, str, str]] = [
    # (category, display_name, color)
    ("cpu", "CPU", "#58a6ff"),         # blue
    ("gpu", "GPU", "#3fb950"),         # green
    ("motherboard", "Motherboard", "#d29922"),  # orange
    ("storage", "Storage", "#a371f7"), # purple
]


class ChartView(QWidget):
    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._window = config.chart_window_seconds

        self._plot = pg.PlotWidget()
        self._plot.setLabel("left", "Temperature", units="°C")
        self._plot.setLabel("bottom", "Time", units="s ago")
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._plot.addLegend(offset=(-10, 10))
        self._plot.setMouseEnabled(x=True, y=False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

        # category -> (times_deque, values_deque, curve)
        self._series: dict[str, tuple[Deque[float], Deque[float], pg.PlotDataItem]] = {}
        self._init_series()

    def _init_series(self) -> None:
        for category, name, color in _CATEGORIES:
            times: Deque[float] = deque()
            values: Deque[float] = deque()
            curve = self._plot.plot(
                x=list(times),
                y=list(values),
                pen=pg.mkPen(color=color, width=2),
                name=name,
            )
            self._series[category] = (times, values, curve)

    def push_snapshot(self, snap: HardwareSnapshot) -> None:
        """Append the hottest sensor from each category at this snapshot."""
        now = snap.timestamp

        # Compute max celsius per category from this snapshot
        per_cat_max: dict[str, Optional[float]] = {}
        for t in snap.temps:
            if t.celsius is None:
                continue
            cur = per_cat_max.get(t.category)
            if cur is None or t.celsius > cur:
                per_cat_max[t.category] = t.celsius

        # Append to each category's rolling window
        for category, (times, values, _curve) in self._series.items():
            val = per_cat_max.get(category)
            if val is None:
                continue
            times.append(now)
            values.append(val)

        # Trim and redraw
        self._trim(now)
        self._redraw()

    def _trim(self, now: float) -> None:
        cutoff = now - self._window
        for _key, (times, values, _curve) in self._series.items():
            while times and times[0] < cutoff:
                times.popleft()
                values.popleft()

    def _redraw(self) -> None:
        for _key, (times, values, curve) in self._series.items():
            if not times:
                continue
            xs = np.fromiter(times, dtype=np.float64)
            # seconds-ago: 0 = rightmost (now), negative to the left
            xs = xs - xs[-1]
            curve.setData(xs, np.fromiter(values, dtype=np.float64))

    def clear(self) -> None:
        """Wipe the in-memory data and hide all curves, but keep the
        PlotDataItem objects alive so the next push_snapshot() re-populates
        them via setData(). This preserves the legend."""
        for times, values, curve in self._series.values():
            times.clear()
            values.clear()
            curve.clear()  # removes the data but keeps the item (and legend entry)