"""Thống kê setup trên dữ liệu đã lưu; không gọi SSI và không ghi SQLite."""

import os as _radar_os, sys as _radar_sys
from pathlib import Path as _RadarPath
_radar_root = _RadarPath(__file__).resolve().parents[2]
_radar_sys.path.insert(0, str(_radar_root / "src"))
_radar_os.chdir(_radar_root)
from contextlib import closing
from pathlib import Path

import pandas as pd

from data import db
from data.ingest import load_universe
from analytics.setup_probability import build_setup_outcomes, summarize_setups

ASOF = "2026-11-16"
DB_PATH = "storage/radar.db"


def main():
    symbols = list(dict.fromkeys(load_universe()))
    with closing(db.connect_readonly(DB_PATH)) as conn:
        conn.execute("BEGIN")
        frames = {symbol: db.load_ohlc(conn, symbol) for symbol in symbols}
        issues = pd.read_sql_query("SELECT symbol, trading_date, severity FROM quality_issues", conn)
    outcomes = build_setup_outcomes(frames, ASOF, issues)
    summary = summarize_setups(outcomes)
    Path("report").mkdir(exist_ok=True)
    outcomes.to_csv("report/setup_outcomes.csv", index=False, encoding="utf-8-sig")
    summary.to_csv("report/setup_probability.csv", index=False, encoding="utf-8-sig")
    display = summary.copy()
    for column in ("probability", "ci_low", "ci_high"):
        display[column] = (display[column] * 100).round(2)
    print(f"Dữ liệu đến {ASOF}; ba cột probability/ci_low/ci_high hiển thị theo %.")
    print(display.to_string(index=False))
    print("Đã lưu report/setup_outcomes.csv và report/setup_probability.csv")


if __name__ == "__main__":
    # CLI tiếng Việt dùng UTF-8 cả khi stdout/stderr bị chuyển vào pipe trên Windows.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
