"""Verify config_store load/save round-trip."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thermal_monitor.config import AppConfig, DEFAULT_THRESHOLDS
from thermal_monitor.config_store import load_config, save_config


def main() -> int:
    # 1. save
    cfg = AppConfig()
    cfg.thresholds = {"cpu": 75.0, "gpu": 90.0, "motherboard": 65.0, "storage": 50.0}
    cfg.poll_interval_ms = 5000

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "config.json"
        assert save_config(cfg, p), "save_config returned False"

        # 2. load
        loaded = load_config(p)
        assert loaded is not None, "load_config returned None"
        assert loaded.thresholds["cpu"] == 75.0, f"cpu: {loaded.thresholds['cpu']}"
        assert loaded.thresholds["gpu"] == 90.0
        assert loaded.poll_interval_ms == 5000
        print(f"round-trip OK: {loaded.thresholds}, interval={loaded.poll_interval_ms}ms")

        # 3. corrupt file -> None
        p.write_text("this is not JSON {")
        assert load_config(p) is None, "corrupt file should return None"
        print("corrupt-file fallback OK")

        # 4. missing file -> None
        p.unlink()
        assert load_config(p) is None
        print("missing-file fallback OK")

        # 5. partial JSON -> defaults merged in
        p.write_text('{"thresholds": {"cpu": 60.0}}')
        loaded = load_config(p)
        assert loaded is not None
        assert loaded.thresholds["cpu"] == 60.0
        # motherboard should fall back to default
        assert loaded.thresholds["motherboard"] == DEFAULT_THRESHOLDS["motherboard"]
        print(f"partial JSON merge OK: {loaded.thresholds}")

    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())