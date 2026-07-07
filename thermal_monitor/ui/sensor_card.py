"""Sensor card widget — a single big number with category + color-coded state."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


# 颜色阶梯: 正常/警告/严重
_COLOR_NORMAL = "#3fb950"     # 绿
_COLOR_WARNING = "#d29922"    # 橙
_COLOR_CRITICAL = "#f85149"   # 红
_COLOR_NA = "#8b949e"         # 灰


def _temp_color(celsius: Optional[float], warn: float, crit: float) -> str:
    if celsius is None:
        return _COLOR_NA
    if celsius >= crit:
        return _COLOR_CRITICAL
    if celsius >= warn:
        return _COLOR_WARNING
    return _COLOR_NORMAL


class SensorCard(QFrame):
    """A card showing one sensor's current reading + label + sub-info line."""

    def __init__(
        self,
        category: str,
        title: str,
        unit: str = "°C",
        warn_threshold: float = 80.0,
        crit_threshold: float = 90.0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._category = category
        self._unit = unit
        self._warn = warn_threshold
        self._crit = crit_threshold

        self.setObjectName("sensorCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(180)
        self.setMinimumHeight(120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        self._title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(False)
        self._title_label.setFont(title_font)
        self._title_label.setStyleSheet("color: #8b949e;")

        self._value_label = QLabel("N/A")
        value_font = QFont()
        value_font.setPointSize(32)
        value_font.setBold(True)
        self._value_label.setFont(value_font)
        self._value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._value_label.setStyleSheet(f"color: {_COLOR_NA};")

        self._sub_label = QLabel("—")
        sub_font = QFont()
        sub_font.setPointSize(9)
        self._sub_label.setFont(sub_font)
        self._sub_label.setStyleSheet("color: #8b949e;")
        self._sub_label.setWordWrap(True)

        layout.addWidget(self._title_label)
        layout.addWidget(self._value_label)
        layout.addWidget(self._sub_label)
        layout.addStretch(1)

    def update_reading(
        self,
        value: Optional[float],
        sub_text: str = "",
        source: str = "",
    ) -> None:
        if value is None:
            self._value_label.setText("N/A")
            self._value_label.setStyleSheet(f"color: {_COLOR_NA};")
        else:
            self._value_label.setText(f"{value:.1f}{self._unit}")
            self._value_label.setStyleSheet(
                f"color: {_temp_color(value, self._warn, self._crit)};"
            )
        bits = []
        if sub_text:
            bits.append(sub_text)
        if source:
            bits.append(f"src: {source}")
        self._sub_label.setText(" · ".join(bits) if bits else "—")
