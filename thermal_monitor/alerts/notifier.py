"""Alert system: scan snapshot, fire AlertEvents, persist to DB.

Levels: ``warning`` (>= warn threshold) | ``critical`` (>= crit = warn + 10°C)
        | ``recovered`` (was alerting, now back below warn).

Hysteresis note: a recovered event fires as soon as the temperature drops
below ``warn`` (not ``warn - 3``). This makes the UI feedback feel snappy.
The flip side is a possible warning -> recovered -> warning ping-pong right
at the threshold; the cooldown (60s) absorbs that.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..collectors.base import HardwareSnapshot
from ..config import AppConfig, FAN_MIN_RPM
from ..data.repository import Repository
from ..utils import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class AlertEvent:
    category: str
    label: str
    level: str  # "warning" | "critical" | "recovered"
    value: float
    threshold: float


class AlertNotifier:
    def __init__(
        self,
        config: AppConfig,
        repository: Repository,
        on_event: Optional[Callable[[AlertEvent], None]] = None,
    ) -> None:
        self._config = config
        self._repo = repository
        self._on_event = on_event
        # sensor_key -> last alert ts (for cooldown)
        self._last_alert: dict[str, float] = {}
        # sensor_key -> current state: None | "warning" | "critical"
        self._state: dict[str, Optional[str]] = {}

    def scan(self, snap: HardwareSnapshot) -> list[AlertEvent]:
        events: list[AlertEvent] = []
        now = snap.timestamp

        for t in snap.temps:
            if t.celsius is None:
                continue
            ev = self._eval_temp(t.category, t.label, t.celsius, now)
            if ev:
                events.append(ev)
                # recovered events are logged separately (no cooldown), but we
                # still persist them so the alerts tab shows the full lifecycle.
                self._repo.log_alert(
                    category=ev.category,
                    label=ev.label,
                    level=ev.level,
                    value=ev.value,
                    threshold=ev.threshold,
                    message=self._format_message(ev),
                )
                if self._on_event:
                    self._on_event(ev)

        for f in snap.fans:
            if f.rpm is None or f.rpm == 0:
                continue
            key = f"fan:{f.label}"
            prev = self._state.get(key)
            if f.rpm < FAN_MIN_RPM and prev != "warning":
                if now - self._last_alert.get(key, 0) >= self._config.alert_cooldown_seconds:
                    self._state[key] = "warning"
                    self._last_alert[key] = now
                    ev = AlertEvent(
                        category="fan",
                        label=f.label,
                        level="warning",
                        value=float(f.rpm),
                        threshold=float(FAN_MIN_RPM),
                    )
                    events.append(ev)
                    self._repo.log_alert(
                        category=ev.category,
                        label=ev.label,
                        level=ev.level,
                        value=ev.value,
                        threshold=ev.threshold,
                        message=f"Fan {f.label} low: {int(f.rpm)} RPM < {FAN_MIN_RPM}",
                    )
                    if self._on_event:
                        self._on_event(ev)
            elif f.rpm >= FAN_MIN_RPM and prev == "warning":
                self._state[key] = None
                ev = AlertEvent(
                    category="fan",
                    label=f.label,
                    level="recovered",
                    value=float(f.rpm),
                    threshold=float(FAN_MIN_RPM),
                )
                events.append(ev)
                self._repo.log_alert(
                    category=ev.category,
                    label=ev.label,
                    level=ev.level,
                    value=ev.value,
                    threshold=ev.threshold,
                    message=f"Fan {f.label} recovered: {int(f.rpm)} RPM",
                )
                if self._on_event:
                    self._on_event(ev)

        return events

    # --- internals -------------------------------------------------------

    def _eval_temp(
        self, category: str, label: str, celsius: float, now: float
    ) -> Optional[AlertEvent]:
        warn = self._config.thresholds.get(category, 80.0)
        crit = warn + 10.0
        key = f"temp:{category}:{label}"
        prev = self._state.get(key)  # None | "warning" | "critical"

        # Critical zone
        if celsius >= crit:
            if prev == "critical":
                return None  # already in critical, no event
            self._state[key] = "critical"
            if now - self._last_alert.get(key, 0) < self._config.alert_cooldown_seconds:
                return None
            self._last_alert[key] = now
            return AlertEvent(
                category=category, label=label,
                level="critical", value=celsius, threshold=crit,
            )

        # Warning zone
        if celsius >= warn:
            if prev in ("warning", "critical"):
                return None  # already alerting, no event
            self._state[key] = "warning"
            if now - self._last_alert.get(key, 0) < self._config.alert_cooldown_seconds:
                return None
            self._last_alert[key] = now
            return AlertEvent(
                category=category, label=label,
                level="warning", value=celsius, threshold=warn,
            )

        # Below warn — possible recovery
        if prev is not None:
            self._state[key] = None
            return AlertEvent(
                category=category, label=label,
                level="recovered", value=celsius, threshold=warn,
            )
        return None

    @staticmethod
    def _format_message(ev: AlertEvent) -> str:
        if ev.level == "recovered":
            return f"RECOVERED: {ev.label} back to {ev.value:.1f}°C (below {ev.threshold:.0f}°C)"
        return f"{ev.level.upper()}: {ev.label} {ev.value:.1f}°C exceeds {ev.threshold:.0f}°C"