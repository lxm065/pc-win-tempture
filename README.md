# PC 温度监控 (PC Temperature Monitor)

桌面端硬件温度监控软件，Windows 平台。Python + PySide6。

![platform](https://img.shields.io/badge/platform-Windows-blue) ![python](https://img.shields.io/badge/python-3.10%2B-green) ![license](https://img.shields.io/badge/license-MIT-lightgrey)

## 功能

- **CPU** 温度（每核 + 封装）+ 12 核使用率
- **GPU** 温度 + 使用率（NVIDIA 走 `nvidia-smi`，其它走 WMI）
- **主板** 多路温度（Nuvoton / ITE Super I/O 芯片）
- **存储** 温度（NVMe / SATA SSD / HDD）
- **风扇** 转速
- 实时数字卡片 + **4 条主曲线**（CPU/GPU/主板/存储最高温）
- **SQLite** 持久化历史（默认 3 天自动清理）
- 阈值告警（warning / critical / **recovered** 三态）+ 托盘通知
- critical 时**任务栏闪烁 + 弹窗到前面 + 三声急促蜂鸣**
- 声音可关（Settings → Alert Sound）
- 系统托盘常驻
- **设置对话框**（Settings…）：阈值 / 采样间隔 / 图表窗口 / DB 保留天数 / 声音开关 / Test Alert / Test Sound

## 技术栈

- Python 3.10+ / PySide6 (Qt 6) / pyqtgraph
- 数据源：psutil + WMI (Windows) + `nvidia-smi` (NVIDIA GPU) + **LibreHardwareMonitor HTTP server**（CPU/主板/存储温度）
- SQLite (内置)

## 快速开始

```bat
:: 首次运行：双击 start.bat
:: 它会：
::   1. 创建 venv
::   2. 装依赖
::   3. 启动 LibreHardwareMonitor（如果没在跑）
::   4. 启动主程序
start.bat
```

或者手动：

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 拿全传感器数据

Win 11 默认 WMI/ACPI **不暴露** CPU 温度、主板温度、风扇转速、硬盘 SMART 温度。装 [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases) 解压后：

1. 首次运行 `LibreHardwareMonitor.exe`（**右键 → 以管理员身份运行**）
2. 顶部菜单 **Options** → **Remote Web Server** → 勾选 **Enable**
3. 端口默认 `8085`，关掉 LHM 后让 start.bat 帮你重启（也得以管理员身份）

本程序自动连 `http://127.0.0.1:8085/data.json` 拉数据，无需改代码。

## 项目结构

```
pc-temp-monitor/
├── main.py                    # 入口
├── start.bat                  # 一键启动（建 venv + 装依赖 + 启 LHM + 启主程序）
├── requirements.txt
├── README.md
├── thermal_monitor/
│   ├── app.py                 # QApplication 入口
│   ├── config.py              # 阈值 + 采样间隔 + 图表窗口 + DB 保留 + 声音
│   ├── config_store.py        # JSON 持久化
│   ├── collectors/
│   │   ├── aggregator.py
│   │   ├── cpu.py             # CPU 温度 + 使用率
│   │   ├── gpu.py             # GPU 走 nvidia-smi / WMI
│   │   ├── motherboard.py
│   │   ├── storage.py
│   │   └── lhm.py             # LibreHardwareMonitor WMI + HTTP 客户端
│   ├── data/
│   │   ├── schema.py
│   │   └── repository.py      # SQLite 时序存储
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── sensor_card.py
│   │   ├── chart_view.py      # 4 条 category 曲线
│   │   ├── threshold_dialog.py
│   │   └── tray.py
│   ├── alerts/
│   │   ├── notifier.py        # warning/critical/recovered 状态机
│   │   └── sound.py           # winsound.Beep 异步播放
│   └── utils/
│       └── logger.py
├── tests/                     # smoke / probe 脚本
└── data/                      # 运行时（不入 git）
    ├── thermal.db
    └── config.json
```

## 已知限制

- Win 默认 WMI 不暴露 CPU/主板/存储温度 → **装 LibreHardwareMonitor 解决**
- AMD/Intel 核显温度 LHM 不一定支持
- 风扇转速依赖主板 EC + Super I/O 芯片，旧主板可能无
- 告警声音在 Windows 用 `winsound.Beep`；非 Windows 静默

## License

MIT
