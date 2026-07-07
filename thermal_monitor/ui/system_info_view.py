"""System info tab — read-only view of PC hardware at a glance.

Pulls a snapshot from ``thermal_monitor.system_info.collect_system_info()``
at construction and on Refresh. Groups info into collapsible-style cards
(OS / CPU / Motherboard / Memory / GPU / Storage / Network).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..system_info import collect_system_info


def _kv(form: QFormLayout, key: str, value: str) -> None:
    """Add a label + value row. Value is selectable text."""
    label = QLabel(value)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    label.setWordWrap(True)
    form.addRow(QLabel(key + ":"), label)


class SystemInfoView(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)  # placeholder until first refresh
        self._scroll.setWidget(self._container)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        # Refresh button row
        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)
        root.addWidget(self._scroll, 1)

        self.refresh()

    # --- public ---------------------------------------------------------

    def refresh(self) -> None:
        """Re-query hardware info and rebuild the cards."""
        # Wipe existing cards (but keep the trailing stretch item)
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        info = collect_system_info()
        self._build_cards(info)

    # --- card builders --------------------------------------------------

    def _add_card(self, title: str, form: QFormLayout) -> None:
        box = QGroupBox(title)
        box.setLayout(form)
        # Insert before the trailing stretch
        self._layout.insertWidget(self._layout.count() - 1, box)

    def _build_cards(self, info: dict) -> None:
        # OS
        os_form = QFormLayout()
        _kv(os_form, "Platform", info.get("os", "N/A"))
        _kv(os_form, "Version", info.get("os_version", "N/A"))
        _kv(os_form, "Hostname", info.get("hostname", "N/A"))
        _kv(os_form, "User", info.get("user", "N/A"))
        _kv(os_form, "Architecture", info.get("arch", "N/A"))
        _kv(os_form, "Python", info.get("python", "N/A"))
        self._add_card("Operating System", os_form)

        # CPU
        cpu_form = QFormLayout()
        _kv(cpu_form, "Model", info.get("cpu_name", "N/A"))
        _kv(
            cpu_form,
            "Cores",
            f"{info.get('cpu_cores_physical', '?')} physical / {info.get('cpu_cores_logical', '?')} logical",
        )
        cur = info.get("cpu_freq_current")
        mx = info.get("cpu_freq_max")
        mn = info.get("cpu_freq_min")
        if cur:
            freq_str = f"{cur / 1000:.2f} GHz"
            if mx and mn and mn > 0:
                freq_str += f"  (min {mn / 1000:.2f} / max {mx / 1000:.2f})"
            _kv(cpu_form, "Frequency", freq_str)
        l2 = info.get("cpu_l2_cache_kb")
        l3 = info.get("cpu_l3_cache_kb")
        cache_str = []
        if l2:
            cache_str.append(f"L2 {l2} KB")
        if l3:
            cache_str.append(f"L3 {l3} KB")
        if cache_str:
            _kv(cpu_form, "Cache", " / ".join(cache_str))
        self._add_card("CPU", cpu_form)

        # Motherboard
        mb_form = QFormLayout()
        _kv(mb_form, "Vendor", info.get("motherboard_vendor", "N/A"))
        _kv(mb_form, "Product", info.get("motherboard_product", "N/A"))
        sn = info.get("motherboard_serial", "")
        if sn:
            _kv(mb_form, "Serial", sn)
        _kv(mb_form, "BIOS Vendor", info.get("bios_vendor", "N/A"))
        _kv(mb_form, "BIOS Version", info.get("bios_version", "N/A"))
        bd = info.get("bios_date", "")
        if bd:
            # Trim the WMI datetime: "20240101000000.000000+000" -> "2024-01-01"
            bd_clean = bd[:8] if len(bd) >= 8 else bd
            if len(bd_clean) == 8 and bd_clean.isdigit():
                bd_clean = f"{bd_clean[:4]}-{bd_clean[4:6]}-{bd_clean[6:8]}"
            _kv(mb_form, "BIOS Date", bd_clean)
        self._add_card("Motherboard", mb_form)

        # Memory
        mem_form = QFormLayout()
        mem_total = info.get("memory_total_bytes", 0)
        if mem_total:
            _kv(mem_form, "Total", f"{mem_total / 1024 ** 3:.1f} GB ({mem_total:,} bytes)")
        speed = info.get("memory_speed_mhz")
        if speed:
            _kv(mem_form, "Speed", f"{int(speed)} MHz")
        self._add_card("Memory", mem_form)

        # GPU
        gpu_form = QFormLayout()
        for idx, g in enumerate(info.get("gpus", []), 1):
            vram = g.get("vram_bytes", 0)
            # WMI Win32_VideoController.AdapterRAM is buggy on many GPUs
            # (returns -1 = "unknown"). Treat <=0 as missing rather than
            # printing "-0.0 GB".
            vram_str = ""
            if vram and vram > 0:
                vram_str = f"  ({vram / 1024 ** 3:.1f} GB)"
            elif vram == -1 or vram == 0:
                vram_str = "  (VRAM unknown via WMI)"
            line = g.get("name", "N/A") + vram_str
            drv = g.get("driver", "")
            if drv:
                line += f"\n  driver: {drv}"
            _kv(gpu_form, f"GPU {idx - 1}", line)
        if not info.get("gpus"):
            _kv(gpu_form, "GPU", "N/A")
        self._add_card("GPU", gpu_form)

        # Storage
        disk_form = QFormLayout()
        for idx, d in enumerate(info.get("disks", []), 1):
            total = d.get("total_bytes", 0)
            used = d.get("used_bytes", 0)
            pct = (used / total * 100) if total else 0
            label = d.get("mountpoint", "?")
            if d.get("model"):
                label += f"  ({d['model']})"
            _kv(
                disk_form,
                f"Disk {idx - 1}",
                f"{label}\n  {d.get('fstype', '?')}  ·  "
                f"{used / 1024 ** 3:.1f} / {total / 1024 ** 3:.1f} GB  ({pct:.0f}%)",
            )
        if not info.get("disks"):
            _kv(disk_form, "Storage", "N/A")
        self._add_card("Storage", disk_form)

        # Network
        net_form = QFormLayout()
        for idx, n in enumerate(info.get("nics", []), 1):
            mac = n.get("mac", "")
            mac_str = f"  ·  {mac}" if mac else ""
            _kv(net_form, f"NIC {idx - 1}", f"{n.get('name', '?')}\n  {n.get('ip', '?')}{mac_str}")
        if not info.get("nics"):
            _kv(net_form, "Network", "No active IPv4 NIC")
        self._add_card("Network", net_form)