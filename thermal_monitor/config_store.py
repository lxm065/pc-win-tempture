"""JSON persistence for AppConfig.

Saves to ``data/config.json`` so user-edited thresholds (and other tunables)
survive restarts. Bad / missing files are tolerated — we fall back to defaults
rather than crashing the UI.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .config import AppConfig, CONFIG_PATH

log = logging.getLogger(__name__)


def save_config(cfg: AppConfig, path: Path = CONFIG_PATH) -> bool:
    """Write the config to disk. Returns True on success."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as exc:
        log.warning("save_config failed: %s", exc)
        return False


def load_config(path: Path = CONFIG_PATH) -> Optional[AppConfig]:
    """Load a saved config, or return None if the file is missing/corrupt.

    The caller should fall back to ``AppConfig()`` defaults when this returns None."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("load_config: %s is corrupt (%s); using defaults", path, exc)
        return None
    if not isinstance(raw, dict):
        log.warning("load_config: %s is not a JSON object; using defaults", path)
        return None
    # Merge: any missing field falls back to the AppConfig default.
    defaults = asdict(AppConfig())
    # Capture the default thresholds dict BEFORE defaults.update() potentially
    # overwrites it with a partial raw value.
    default_thresholds = dict(defaults.get("thresholds", {}))
    defaults.update(raw)
    # Deep-merge thresholds so a partial {"thresholds": {"cpu": 60}} doesn't
    # wipe out motherboard/gpu/storage keys.
    if "thresholds" in defaults and isinstance(defaults["thresholds"], dict):
        merged = default_thresholds
        merged.update(defaults["thresholds"])
        defaults["thresholds"] = merged
    elif "thresholds" in defaults and not isinstance(defaults["thresholds"], dict):
        # Threshold value was somehow not a dict — restore default
        defaults["thresholds"] = default_thresholds
    # Migration: pre-v2.2 saved retention_days was 7 (old default). We changed
    # the default to 3. Migrate the saved value so the new default kicks in
    # for users who never explicitly set retention. Users who *did* set
    # something else (1, 2, 5, 10, etc.) keep their value.
    if isinstance(raw.get("history_retention_days"), int) and raw["history_retention_days"] == 7:
        defaults["history_retention_days"] = defaults.get("history_retention_days", 3)
    try:
        return AppConfig(**defaults)
    except Exception as exc:
        log.warning("load_config: AppConfig(**data) failed (%s); using defaults", exc)
        return None