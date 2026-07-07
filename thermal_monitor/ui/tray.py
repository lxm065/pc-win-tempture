"""System tray icon with quick-view menu and a single line of hottest sensor."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget


def _make_temp_icon(celsius: Optional[float], warn: float = 80.0, crit: float = 90.0) -> QIcon:
    """Render a tiny colored thermometer glyph as the tray icon."""
    pix = QPixmap(QSize(64, 64))
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    if celsius is None:
        color = QColor("#8b949e")
    elif celsius >= crit:
        color = QColor("#f85149")
    elif celsius >= warn:
        color = QColor("#d29922")
    else:
        color = QColor("#3fb950")
    p.setBrush(color)
    p.setPen(QColor("#0d1117"))
    # Thermometer body
    p.drawRoundedRect(26, 8, 12, 36, 6, 6)
    p.drawEllipse(22, 40, 20, 20)
    p.end()
    return QIcon(pix)


class TrayIcon(QSystemTrayIcon):
    """Tray icon + menu. Owns no model — main window pushes updates."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._last_celsius: Optional[float] = None
        self.setIcon(_make_temp_icon(None))
        self.setToolTip("PC Temperature Monitor")

        menu = QMenu(parent)
        self._show_action = QAction("Show Window", menu)
        self._quit_action = QAction("Quit", menu)
        menu.addAction(self._show_action)
        menu.addSeparator()
        menu.addAction(self._quit_action)
        self.setContextMenu(menu)
        self._show_action.triggered.connect(self._on_show)
        self._quit_action.triggered.connect(self._on_quit)
        self.activated.connect(self._on_activated)

        self.show_window_requested = None  # callable
        self.quit_requested = None  # callable

    def set_hottest(self, celsius: Optional[float]) -> None:
        self._last_celsius = celsius
        self.setIcon(_make_temp_icon(celsius))
        if celsius is None:
            self.setToolTip("PC Temperature Monitor — no sensor data")
        else:
            self.setToolTip(f"PC Temperature Monitor — hottest: {celsius:.1f}°C")

    def _on_show(self) -> None:
        if self.show_window_requested:
            self.show_window_requested()

    def _on_quit(self) -> None:
        if self.quit_requested:
            self.quit_requested()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.show_window_requested:
                self.show_window_requested()
