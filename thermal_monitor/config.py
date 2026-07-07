"""Application config: thresholds, polling intervals, persistence window."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


# 仓库根目录 = pc-temp-monitor/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "thermal.db"
CONFIG_PATH = DATA_DIR / "config.json"


# 温度阈值（摄氏度）—— 超出会触发告警
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "cpu": 80.0,
    "gpu": 85.0,
    "motherboard": 70.0,
    "storage": 55.0,
}

# 风扇转速告警（rpm）—— 低于这个值视为"风扇异常"
FAN_MIN_RPM = 200


@dataclass
class AppConfig:
    """运行时可调的参数。"""

    # 采集间隔（毫秒）
    poll_interval_ms: int = 2000

    # 历史曲线在内存中保留的秒数
    chart_window_seconds: int = 300  # 5 分钟

    # SQLite 保留天数（超过会被 prune 删除）
    history_retention_days: int = 3

    # 阈值告警冷却时间（秒）—— 同一传感器连续告警的最短间隔
    alert_cooldown_seconds: float = 60.0

    # 告警声音（Windows 用 winsound.Beep 播频率；非 Windows 静默）
    alert_sound_enabled: bool = True

    # 启动时是否最小化到托盘
    start_minimized: bool = False

    # 关闭主窗口时是否真退出（False = 收到托盘）
    quit_on_window_close: bool = False

    # 阈值（运行时可调）
    thresholds: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))


def get_config() -> AppConfig:
    """每次调用都返回新实例，避免脏状态。"""
    return AppConfig()
