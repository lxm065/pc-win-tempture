"""Settings dialog — combines alert thresholds + polling/chart tunables.

The original "Thresholds" name is preserved as the window title prefix so
existing muscle memory keeps working, but poll interval and chart window
have been added.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..alerts.notifier import AlertEvent
from ..config import AppConfig


class ThresholdDialog(QDialog):
    def __init__(
        self,
        config: AppConfig,
        on_test: Optional[Callable[[AlertEvent], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings & Thresholds")
        self.setModal(True)
        self.setMinimumWidth(380)
        self._config = config
        self._on_test = on_test

        root = QVBoxLayout(self)

        # === Sampling group =============================================
        sample_box = QGroupBox("Sampling")
        sample_form = QFormLayout(sample_box)

        self._interval_input = QSpinBox()
        self._interval_input.setRange(500, 60000)
        self._interval_input.setSingleStep(500)
        self._interval_input.setSuffix(" ms")
        self._interval_input.setValue(int(config.poll_interval_ms))
        sample_form.addRow("Poll interval", self._interval_input)

        self._window_input = QSpinBox()
        self._window_input.setRange(30, 3600)
        self._window_input.setSingleStep(30)
        self._window_input.setSuffix(" s")
        self._window_input.setValue(int(config.chart_window_seconds))
        sample_form.addRow("Chart window", self._window_input)

        self._retention_input = QSpinBox()
        self._retention_input.setRange(1, 30)
        self._retention_input.setSingleStep(1)
        self._retention_input.setSuffix(" days")
        self._retention_input.setValue(int(config.history_retention_days))
        sample_form.addRow("DB retention", self._retention_input)

        sample_hint = QLabel(
            "Lower interval = more responsive / more CPU & DB writes.\n"
            "Chart window = how far back the rolling chart shows.\n"
            "DB retention = rows older than this are pruned every 10 minutes."
        )
        sample_hint.setStyleSheet("color: #8b949e;")
        sample_form.addRow(sample_hint)

        root.addWidget(sample_box)

        # === Thresholds group ===========================================
        thresh_box = QGroupBox("Alert Thresholds")
        thresh_form = QFormLayout(thresh_box)

        self._inputs: dict[str, QDoubleSpinBox] = {}
        labels = {
            "cpu": "CPU",
            "gpu": "GPU",
            "motherboard": "Motherboard",
            "storage": "Storage",
        }
        for key, name in labels.items():
            spin = QDoubleSpinBox()
            spin.setRange(30.0, 120.0)
            spin.setSingleStep(1.0)
            spin.setSuffix(" °C")
            spin.setValue(config.thresholds.get(key, 80.0))
            thresh_form.addRow(name, spin)
            self._inputs[key] = spin

        thresh_hint = QLabel(
            "Critical alerts fire 10°C above these values.\n"
            "Cooldown between alerts: 60s."
        )
        thresh_hint.setStyleSheet("color: #8b949e;")
        thresh_form.addRow(thresh_hint)

        root.addWidget(thresh_box)

        # === Sound group =================================================
        sound_box = QGroupBox("Alert Sound")
        sound_form = QFormLayout(sound_box)

        self._sound_checkbox = QCheckBox("Play sound on alert")
        self._sound_checkbox.setChecked(bool(config.alert_sound_enabled))
        sound_form.addRow(self._sound_checkbox)

        self._test_sound_btn = QPushButton("Test Sound")
        self._test_sound_btn.clicked.connect(self._on_test_sound_clicked)
        test_sound_row = QHBoxLayout()
        test_sound_row.addWidget(QLabel("Preview:"))
        test_sound_row.addWidget(self._test_sound_btn)
        test_sound_row.addStretch(1)
        sound_form.addRow(test_sound_row)

        sound_hint = QLabel(
            "Critical = 3 short high-pitch beeps\n"
            "Warning  = 1 mid-pitch beep\n"
            "Recovered = 2-tone 'all clear'"
        )
        sound_hint.setStyleSheet("color: #8b949e;")
        sound_form.addRow(sound_hint)

        root.addWidget(sound_box)

        # === Test button + OK/Cancel ====================================
        button_row = QHBoxLayout()
        self._test_btn = QPushButton("Test Alert")
        self._test_btn.setToolTip(
            "Fire one synthetic critical alert per category using the\n"
            "spinbox values currently shown (does not require OK)."
        )
        self._test_btn.clicked.connect(self._on_test_clicked)
        button_row.addWidget(self._test_btn)
        button_row.addStretch(1)

        self._ok_cancel = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._ok_cancel.accepted.connect(self.accept)
        self._ok_cancel.rejected.connect(self.reject)
        button_row.addWidget(self._ok_cancel)

        root.addLayout(button_row)

    # --- accept / test --------------------------------------------------

    def accept(self) -> None:  # type: ignore[override]
        for key, spin in self._inputs.items():
            self._config.thresholds[key] = spin.value()
        self._config.poll_interval_ms = int(self._interval_input.value())
        self._config.chart_window_seconds = int(self._window_input.value())
        self._config.history_retention_days = int(self._retention_input.value())
        self._config.alert_sound_enabled = self._sound_checkbox.isChecked()
        super().accept()

    def _on_test_sound_clicked(self) -> None:
        """Play a short critical pattern so the user can verify volume/levels."""
        try:
            from ..alerts import sound
            sound.play_critical()
        except Exception as exc:
            # Don't let a sound error kill the dialog
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Sound Test Failed", str(exc))

    def _on_test_clicked(self) -> None:
        """Fire one synthetic critical alert per category at threshold+5°C,
        using the spinbox values currently in the dialog (not the saved config)."""
        if not self._on_test:
            return
        for category, spin in self._inputs.items():
            threshold = float(spin.value())
            value = threshold + 5.0
            label = f"[TEST] {category.upper()}"
            ev = AlertEvent(
                category=category,
                label=label,
                level="critical",
                value=value,
                threshold=threshold,
            )
            try:
                self._on_test(ev)
            except Exception:
                # Don't let a test-fire error kill the dialog
                pass