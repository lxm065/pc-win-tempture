"""Application entry point.

Run with: `python main.py`
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_qt_paths() -> None:
    """PySide6 wheels ship their own Qt DLLs under site-packages/PySide6.
    When Python is launched from environments that don't include that
    directory on PATH (PowerShell Start-Process, scheduled tasks, etc.),
    `import PySide6.QtCore` fails with "DLL load failed". Pre-register the
    directory with os.add_dll_directory so Windows can find Qt6Core.dll etc.
    """
    try:
        import PySide6  # type: ignore
    except ImportError:
        return  # let the import fail later with a clearer error

    pyside_dir = Path(PySide6.__file__).resolve().parent
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(pyside_dir))
    # Also include shiboken6 — it ships a few support DLLs too.
    try:
        import shiboken6  # type: ignore

        shiboken_dir = Path(shiboken6.__file__).resolve().parent
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(shiboken_dir))
    except ImportError:
        pass
    # Prepend to PATH for child processes (QSystemTrayIcon spawns helpers).
    os.environ["PATH"] = str(pyside_dir) + os.pathsep + os.environ.get("PATH", "")


_bootstrap_qt_paths()

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon  # noqa: E402

from thermal_monitor.app import AppController  # noqa: E402
from thermal_monitor.config import get_config  # noqa: E402
from thermal_monitor.config_store import load_config  # noqa: E402
from thermal_monitor.utils import get_logger, setup_logging  # noqa: E402


def main() -> int:
    # HiDPI is default in Qt6, but we set it explicitly for predictable sizing.
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("PC Temperature Monitor")
    app.setQuitOnLastWindowClosed(False)  # tray-resident

    setup_logging()
    log = get_logger("main")

    # Bail early if the system can't do a tray icon — software is unusable without it.
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            "System tray not available",
            "This app requires a system tray to run. Your desktop environment does not provide one.",
        )
        return 2

    # Load saved config (thresholds etc.) if present; otherwise use defaults.
    saved = load_config()
    config = saved if saved is not None else get_config()
    if saved is not None:
        log.info("loaded saved config from %s", saved)
    else:
        log.info("no saved config found; using defaults")
    controller = AppController(app, config)

    # Start the polling worker (QThread). Without this, no snapshot_ready
    # signals fire and the UI stays at "Initializing..." forever.
    controller.start()

    # Show window
    if not config.start_minimized:
        controller.show_window()

    # Graceful shutdown
    def on_about_to_quit() -> None:
        log.info("shutting down")
        controller.stop()

    app.aboutToQuit.connect(on_about_to_quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
