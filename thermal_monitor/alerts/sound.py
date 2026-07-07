"""Alert sound playback.

Uses winsound.Beep on Windows (built-in, no extra deps). Playback is fired
on a background daemon thread so the main UI loop is never blocked, even
for triple-beep criticals.

On non-Windows this module silently no-ops — the app still works without
sound, just quieter.
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Optional

from ..utils import get_logger

log = get_logger(__name__)


def _play_pattern(freqs_and_durations: list[tuple[int, int]], gap_ms: int = 100) -> None:
    """Run a beep pattern on a background thread.

    Each tuple is (frequency_hz, duration_ms). A silence gap_ms is inserted
    between consecutive beeps (but not after the last one)."""
    if sys.platform != "win32":
        return
    def _runner() -> None:
        try:
            import winsound  # type: ignore
        except Exception as exc:
            log.debug("winsound import failed: %s", exc)
            return
        try:
            for idx, (freq, dur_ms) in enumerate(freqs_and_durations):
                if freq <= 0 or dur_ms <= 0:
                    continue
                winsound.Beep(int(freq), int(dur_ms))
                if idx < len(freqs_and_durations) - 1 and gap_ms > 0:
                    time.sleep(gap_ms / 1000.0)
        except Exception as exc:
            log.debug("beep playback failed: %s", exc)
    t = threading.Thread(target=_runner, daemon=True, name="alert-sound")
    t.start()


def play_warning() -> None:
    """A single mid-pitch beep (~A5, 250ms)."""
    _play_pattern([(880, 250)])


def play_critical() -> None:
    """Three short high-pitch beeps (~E6, 180ms each) with brief gaps.
    Distinctive enough to cut through music / game audio."""
    _play_pattern([(1320, 180), (1320, 180), (1320, 180)], gap_ms=120)


def play_recovered() -> None:
    """Two-tone 'all clear' (low then slightly higher) — quiet, friendly."""
    _play_pattern([(660, 120), (880, 160)])


def play_test(level: str = "critical") -> None:
    """Convenience for the Settings dialog 'Test Sound' button."""
    if level == "critical":
        play_critical()
    elif level == "recovered":
        play_recovered()
    else:
        play_warning()