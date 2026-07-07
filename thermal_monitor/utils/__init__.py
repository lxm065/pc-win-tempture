"""Lightweight logger — file + stderr, no extra deps."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..config import DATA_DIR

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_FILE = DATA_DIR / "thermal-monitor.log"


def setup_logging(level: int = logging.INFO) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        # 防止重复添加（reload 场景）
        return
    root.setLevel(level)

    fmt = logging.Formatter(_LOG_FORMAT)

    # file
    fh = RotatingFileHandler(_LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # stderr
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
