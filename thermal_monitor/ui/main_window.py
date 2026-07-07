"""Main window — cards row + chart + alerts list + status bar."""
from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..alerts.notifier import AlertEvent
from ..collectors.base import HardwareSnapshot
from ..config import AppConfig
from .chart_view import ChartView
from .sensor_card import SensorCard
from .system_info_view import SystemInfoView
from .tray import TrayIcon


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self.setWindowTitle("PC Temperature Monitor")
        self.resize(1180, 720)
        self.setStyleSheet(_QSS_DARK)

        # --- toolbar ---
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._threshold_action = QAction("Thresholds…", self)
        self._threshold_action.setShortcut(QKeySequence("Ctrl+T"))
        toolbar.addAction(self._threshold_action)

        self._clear_chart_action = QAction("Clear Chart", self)
        toolbar.addAction(self._clear_chart_action)

        self._clear_alerts_action = QAction("Clear Alerts", self)
        self._clear_alerts_action.setShortcut(QKeySequence("Ctrl+L"))
        self._clear_alerts_action.setToolTip("Clear the alerts list display (DB history is preserved)")
        toolbar.addAction(self._clear_alerts_action)

        toolbar.addSeparator()
        self._refresh_action = QAction("Refresh Now", self)
        self._refresh_action.setShortcut(QKeySequence("F5"))
        toolbar.addAction(self._refresh_action)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self._paused_label = QLabel("")
        toolbar.addWidget(self._paused_label)

        # --- top: 4 cards ---
        cards_row = QWidget()
        cards_layout = QHBoxLayout(cards_row)
        cards_layout.setContentsMargins(8, 8, 8, 0)
        cards_layout.setSpacing(8)

        self._card_cpu = SensorCard("cpu", "CPU Temperature", warn_threshold=80.0, crit_threshold=92.0)
        self._card_gpu = SensorCard("gpu", "GPU Temperature", warn_threshold=85.0, crit_threshold=95.0)
        self._card_mobo = SensorCard("motherboard", "Motherboard", warn_threshold=70.0, crit_threshold=85.0)
        self._card_storage = SensorCard("storage", "Storage", warn_threshold=55.0, crit_threshold=70.0)
        cards_layout.addWidget(self._card_cpu)
        cards_layout.addWidget(self._card_gpu)
        cards_layout.addWidget(self._card_mobo)
        cards_layout.addWidget(self._card_storage)

        # --- center: chart ---
        self._chart = ChartView(config)

        # --- right: alerts + fan list ---
        right_panel = QTabWidget()
        right_panel.setMinimumWidth(280)

        self._alert_list = QListWidget()
        right_panel.addTab(self._alert_list, "Alerts")

        self._fan_list = QListWidget()
        right_panel.addTab(self._fan_list, "Fans")

        self._system_view = SystemInfoView()
        right_panel.addTab(self._system_view, "System")

        # --- splitter ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._chart)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        # --- root layout ---
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(cards_row)
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

        # --- status bar ---
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_left = QLabel("Initializing…")
        self._status_right = QLabel("")
        self._status.addWidget(self._status_left, 1)
        self._status.addPermanentWidget(self._status_right)

        # --- tray ---
        self._tray = TrayIcon(self)
        self._tray.show()

        # Callbacks (assigned by app.py)
        self.on_threshold_edit: Optional[Callable[[], None]] = None
        self.on_clear_chart: Optional[Callable[[], None]] = None
        self.on_clear_alerts: Optional[Callable[[], None]] = None
        self.on_refresh: Optional[Callable[[], None]] = None
        self._threshold_action.triggered.connect(
            lambda: self.on_threshold_edit and self.on_threshold_edit()
        )
        self._clear_chart_action.triggered.connect(self._on_clear_chart)
        self._clear_alerts_action.triggered.connect(self._on_clear_alerts)
        self._refresh_action.triggered.connect(
            lambda: self.on_refresh and self.on_refresh()
        )

        # Tray wiring
        self._tray.show_window_requested = self._show_from_tray
        self._tray.quit_requested = self._quit_from_tray

    # --- public update API -----------------------------------------------

    def apply_snapshot(self, snap: HardwareSnapshot, error_count: int) -> None:
        # CPU
        cpu_temps = [t for t in snap.temps if t.category == "cpu" and t.celsius is not None]
        if cpu_temps:
            hottest = max(cpu_temps, key=lambda t: t.celsius)
            self._card_cpu.update_reading(
                hottest.celsius,
                sub_text=f"{len(cpu_temps)} sensor(s) · {hottest.label}",
                source=hottest.source,
            )
        else:
            self._card_cpu.update_reading(None, sub_text="no data", source="—")

        # GPU
        gpu_temps = [t for t in snap.temps if t.category == "gpu" and t.celsius is not None]
        if gpu_temps:
            hottest = max(gpu_temps, key=lambda t: t.celsius)
            gpu_usages = [u for u in snap.usages if "GPU" in u.label.upper() and u.percent is not None]
            sub = hottest.label
            if gpu_usages:
                u = max(gpu_usages, key=lambda x: x.percent or 0)
                sub += f" · {u.percent:.0f}%"
            self._card_gpu.update_reading(hottest.celsius, sub_text=sub, source=hottest.source)
        else:
            gpu_names = [t.label for t in snap.temps if t.category == "gpu"]
            if gpu_names:
                self._card_gpu.update_reading(
                    None,
                    sub_text=f"{gpu_names[0]} (no temp sensor)",
                    source="wmi",
                )
            else:
                self._card_gpu.update_reading(None, sub_text="no GPU detected", source="—")

        # Motherboard
        mobo_temps = [t for t in snap.temps if t.category == "motherboard" and t.celsius is not None]
        if mobo_temps:
            hottest = max(mobo_temps, key=lambda t: t.celsius)
            self._card_mobo.update_reading(hottest.celsius, sub_text=hottest.label, source=hottest.source)
        else:
            self._card_mobo.update_reading(None, sub_text="not exposed by WMI/ACPI", source="—")

        # Storage
        stor_temps = [t for t in snap.temps if t.category == "storage" and t.celsius is not None]
        if stor_temps:
            hottest = max(stor_temps, key=lambda t: t.celsius)
            self._card_storage.update_reading(
                hottest.celsius, sub_text=hottest.label, source=hottest.source
            )
        else:
            self._card_storage.update_reading(None, sub_text="SMART temp not exposed", source="—")

        # Fan list
        self._fan_list.clear()
        if not snap.fans:
            self._fan_list.addItem(
                QListWidgetItem("No fan sensors (WMI does not expose RPM on this board)")
            )
        else:
            for f in snap.fans:
                rpm = f.rpm if f.rpm is not None else 0
                item = QListWidgetItem(f"{f.label}  —  {rpm} RPM  ({f.source})")
                if f.rpm is None or f.rpm < 200:
                    item.setForeground(Qt.red)
                self._fan_list.addItem(item)

        # Chart
        self._chart.push_snapshot(snap)

        # Status bar
        mem = f"  |  RAM: {snap.mem_percent:.0f}%" if snap.mem_percent is not None else ""
        err = f"  |  ⚠ {error_count} sensor(s) unavailable" if error_count else ""
        self._status_left.setText(f"Last update: {_fmt_time(snap.timestamp)}{mem}{err}")
        self._status_right.setText(
            f"interval: {self._config.poll_interval_ms / 1000:.0f}s · window: {self._config.chart_window_seconds}s"
        )

        # Tray
        all_temps = [t.celsius for t in snap.temps if t.celsius is not None]
        hottest_overall = max(all_temps) if all_temps else None
        self._tray.set_hottest(hottest_overall)

    def push_alert(self, event: AlertEvent, force_show_notification: bool = False) -> None:
        if event.level == "critical":
            icon = "🔴"
            line = f"{icon} {event.label}  {event.value:.1f}°C  (>{event.threshold:.0f}°C)"
            item = QListWidgetItem(line)
            item.setForeground(Qt.red)
        elif event.level == "recovered":
            icon = "✅"
            line = f"{icon} {event.label}  recovered  ({event.value:.1f}°C)"
            item = QListWidgetItem(line)
            item.setForeground(Qt.darkGreen)
        else:  # warning
            icon = "🟡"
            line = f"{icon} {event.label}  {event.value:.1f}°C  (>{event.threshold:.0f}°C)"
            item = QListWidgetItem(line)
        self._alert_list.insertItem(0, item)
        # Cap to last 200
        while self._alert_list.count() > 200:
            self._alert_list.takeItem(self._alert_list.count() - 1)
        # Tray notification: critical/warning always when forced or window hidden.
        # recovered never notifies — it's a quiet "back to normal".
        if event.level == "recovered":
            return
        if force_show_notification or not self.isActiveWindow():
            self._tray.showMessage(
                "Temperature Alert",
                f"{event.label}: {event.value:.1f}°C exceeds {event.threshold:.0f}°C",
                QSystemTrayIcon.MessageIcon.Warning,
                4000,
            )

    # --- window/tray integration ----------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._config.quit_on_window_close:
            event.accept()
            return
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "PC Temperature Monitor",
            "Still running in the system tray. Right-click the icon to quit.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.instance().quit()

    def _on_clear_chart(self) -> None:
        self._chart.clear()
        if self.on_clear_chart:
            self.on_clear_chart()

    def _on_clear_alerts(self) -> None:
        """Wipe the alerts list display. DB rows in data/thermal.db are kept
        intact (queryable later via Repository.get_recent_alerts)."""
        self._alert_list.clear()
        if self.on_clear_alerts:
            self.on_clear_alerts()

    def set_paused(self, paused: bool) -> None:
        self._paused_label.setText("  ⏸ PAUSED" if paused else "")


def _fmt_time(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


_QSS_DARK = """
QMainWindow, QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
}
QToolBar {
    background-color: #161b22;
    border: none;
    padding: 4px;
    spacing: 6px;
}
QToolBar QToolButton {
    color: #c9d1d9;
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}
QToolBar QToolButton:hover { background: #21262d; }
QStatusBar {
    background: #161b22;
    color: #8b949e;
}
QTabWidget::pane {
    border: 1px solid #30363d;
    background: #0d1117;
}
QTabBar::tab {
    background: #161b22;
    color: #8b949e;
    padding: 6px 14px;
    border: 1px solid #30363d;
    border-bottom: none;
}
QTabBar::tab:selected {
    background: #0d1117;
    color: #c9d1d9;
}
QListWidget {
    background: #0d1117;
    border: none;
    color: #c9d1d9;
}
QListWidget::item { padding: 4px 6px; }
QListWidget::item:selected { background: #1f6feb; color: white; }
QSplitter::handle { background: #21262d; }
QFrame#sensorCard {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
}
"""
