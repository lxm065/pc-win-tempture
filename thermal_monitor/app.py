"""QApplication wiring: collector worker, repository, alert notifier, main window."""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .alerts.notifier import AlertEvent, AlertNotifier
from .alerts import sound as alert_sound
from .collectors.aggregator import collect_snapshot
from .collectors.base import HardwareSnapshot
from .config import AppConfig, get_config
from .config_store import save_config
from .data.repository import Repository
from .ui.main_window import MainWindow
from .ui.threshold_dialog import ThresholdDialog
from .utils import get_logger, setup_logging

log = get_logger(__name__)


class CollectorWorker(QObject):
    """Runs the polling loop on its own thread. Emits a HardwareSnapshot
    per cycle. Never touches UI objects directly."""

    snapshot_ready = Signal(object)  # HardwareSnapshot
    finished = Signal()

    def __init__(self, config: AppConfig, repository: Repository, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._repo = repository
        self._stop = False
        self._pause = False
        self._pause_cond_tick = 0  # for log throttling

    @Slot()
    def stop(self) -> None:
        self._stop = True

    @Slot(bool)
    def set_paused(self, paused: bool) -> None:
        self._pause = paused

    @Slot()
    def run(self) -> None:
        log.info("collector worker started, interval=%dms", self._config.poll_interval_ms)
        next_tick = time.monotonic()
        while not self._stop:
            now = time.monotonic()
            sleep_for = max(0.0, next_tick - now)
            if sleep_for > 0:
                # Sleep in small slices so stop() takes effect quickly
                end = now + sleep_for
                while time.monotonic() < end and not self._stop:
                    time.sleep(min(0.1, end - time.monotonic()))

            if self._stop:
                break

            if self._pause:
                # Still tick so the UI shows it's alive, but don't collect
                self._pause_cond_tick += 1
                if self._pause_cond_tick % 30 == 1:
                    log.debug("collector paused")
                next_tick = time.monotonic() + self._config.poll_interval_ms / 1000.0
                continue

            try:
                snap = collect_snapshot()
                try:
                    self._repo.save_snapshot(snap)
                except Exception as exc:
                    log.warning("save_snapshot failed: %s", exc)
                self.snapshot_ready.emit(snap)
            except Exception as exc:
                log.exception("collect_snapshot crashed: %s", exc)

            next_tick = time.monotonic() + self._config.poll_interval_ms / 1000.0
        log.info("collector worker stopped")
        self.finished.emit()


class AppController(QObject):
    """Owns the worker thread, repository, notifier, and main window.
    Routes signals between them."""

    def __init__(self, app: QApplication, config: AppConfig) -> None:
        super().__init__()
        self._app = app
        self._config = config
        self._repo = Repository()
        self._window = MainWindow(config)
        self._notifier = AlertNotifier(config, self._repo, on_event=self._on_alert)
        self._thread: Optional[QThread] = None
        self._worker: Optional[CollectorWorker] = None
        self._last_error_count: int = 0

        # Wire window callbacks
        self._window.on_threshold_edit = self._edit_thresholds
        self._window.on_clear_chart = self._on_clear_chart
        self._window.on_clear_alerts = self._on_clear_alerts
        self._window.on_refresh = self._force_collect

        # Periodic DB prune: every 10 min, drop rows older than retention_days.
        # Faster cadence keeps file size in check given the high write rate
        # (~17 rows/sec at default 2s poll × 17 sensors).
        self._prune_timer = QTimer(self)
        self._prune_timer.setInterval(10 * 60 * 1000)
        self._prune_timer.timeout.connect(self._prune_db)
        self._prune_timer.start()
        # Also run once at startup to clean up anything left from prior runs
        # (e.g. after a crash or before the timer fires for the first time).
        QTimer.singleShot(5_000, self._prune_db)

    def start(self) -> None:
        self._thread = QThread()
        self._worker = CollectorWorker(self._config, self._repo)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.snapshot_ready.connect(self._on_snapshot)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def stop(self) -> None:
        if self._worker:
            self._worker.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        try:
            self._repo.prune(self._config.history_retention_days)
        except Exception:
            pass
        self._repo.close()

    def show_window(self) -> None:
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    # --- slots -----------------------------------------------------------

    @Slot(object)
    def _on_snapshot(self, snap: HardwareSnapshot) -> None:
        self._last_error_count = len(snap.errors)
        try:
            self._notifier.scan(snap)
        except Exception as exc:
            log.warning("alert scan failed: %s", exc)
        self._window.apply_snapshot(snap, self._last_error_count)

    @Slot(object)
    def _on_alert(self, event: AlertEvent) -> None:
        self._window.push_alert(event)
        # Critical alerts: bring the window to the front and flash the taskbar
        # entry so the user can't miss it. ``alert(duration=0)`` flashes until
        # the window gets focus.
        if event.level == "critical":
            try:
                QApplication.alert(self._window, 0)
                if not self._window.isActiveWindow():
                    self._window.showNormal()
                    self._window.raise_()
                    self._window.activateWindow()
            except Exception as exc:
                log.debug("flash taskbar failed: %s", exc)
        # Audio cue (non-blocking on a daemon thread)
        if self._config.alert_sound_enabled:
            if event.level == "critical":
                alert_sound.play_critical()
            elif event.level == "warning":
                alert_sound.play_warning()
            elif event.level == "recovered":
                alert_sound.play_recovered()

    def _edit_thresholds(self) -> None:
        dlg = ThresholdDialog(self._config, on_test=self._test_alert, parent=self._window)
        if dlg.exec():  # Accepted
            if save_config(self._config):
                log.info("saved config: thresholds=%s", self._config.thresholds)
            else:
                log.warning("failed to save config to disk; thresholds are in-memory only")

    def _test_alert(self, event: AlertEvent) -> None:
        """Synthetic alert fired by ThresholdDialog's Test button.
        Bypasses cooldown + writes DB + pushes UI + shows tray notification."""
        try:
            self._repo.log_alert(
                category=event.category,
                label=event.label,
                level=event.level,
                value=event.value,
                threshold=event.threshold,
                message=f"{event.level.upper()}: {event.value:.1f}°C exceeds {event.threshold:.0f}°C (TEST)",
            )
        except Exception as exc:
            log.warning("test alert DB write failed: %s", exc)
        # Push to UI list + tray (synthetic; doesn't go through cooldown logic)
        self._window.push_alert(event, force_show_notification=True)

    def _on_clear_chart(self) -> None:
        # No chart state to reset on the data side; the in-memory rolling
        # window was already cleared by the view itself.
        pass

    def _on_clear_alerts(self) -> None:
        # UI list was wiped by the view. We deliberately do NOT delete DB
        # rows — they remain queryable via Repository.get_recent_alerts()
        # and visible in the alerts tab after restart if we ever wire a
        # "load history" feature.
        log.info("alerts list cleared by user; DB history preserved")

    def _force_collect(self) -> None:
        """Run one extra collect on the UI thread without touching the
        worker's loop. Calling self._worker.run() from here would deadlock
        because that method is an infinite loop intended to run on the
        QThread, not on the main thread."""
        from .collectors.aggregator import collect_snapshot

        snap = collect_snapshot()
        self._last_error_count = len(snap.errors)
        try:
            self._notifier.scan(snap)
        except Exception as exc:
            log.warning("alert scan failed: %s", exc)
        self._window.apply_snapshot(snap, self._last_error_count)

    def _prune_db(self) -> None:
        try:
            deleted = self._repo.prune(self._config.history_retention_days)
            if deleted:
                log.info("pruned %d old readings", deleted)
        except Exception as exc:
            log.warning("prune failed: %s", exc)
