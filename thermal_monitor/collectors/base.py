"""Shared types for all collectors."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TempReading:
    """A single temperature sample from one sensor."""

    label: str  # e.g. "CPU Package", "GPU 0", "SSD Crucial MX500"
    category: str  # one of: cpu, gpu, motherboard, storage
    celsius: Optional[float]  # None means "sensor exists but no reading"
    source: str  # "wmi" | "nvidia-smi" | "psutil" — for debugging / display

    @property
    def available(self) -> bool:
        return self.celsius is not None


@dataclass(frozen=True)
class FanReading:
    label: str
    rpm: Optional[int]
    source: str

    @property
    def available(self) -> bool:
        return self.rpm is not None and self.rpm > 0


@dataclass(frozen=True)
class UsageReading:
    label: str
    percent: Optional[float]  # 0-100
    source: str

    @property
    def available(self) -> bool:
        return self.percent is not None


@dataclass
class HardwareSnapshot:
    """One polling cycle's worth of data from every sensor."""

    timestamp: float  # epoch seconds
    temps: list[TempReading] = field(default_factory=list)
    fans: list[FanReading] = field(default_factory=list)
    usages: list[UsageReading] = field(default_factory=list)
    mem_percent: Optional[float] = None
    errors: list[str] = field(default_factory=list)  # collector-side warnings

    def by_category(self, category: str) -> list[TempReading]:
        return [t for t in self.temps if t.category == category]
