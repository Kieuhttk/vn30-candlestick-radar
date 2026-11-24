
import os as _radar_os, sys as _radar_sys
from pathlib import Path as _RadarPath
_radar_root = _RadarPath(__file__).resolve().parents[2]
_radar_sys.path.insert(0, str(_radar_root / "src"))
_radar_os.chdir(_radar_root)
from contextlib import closing
from pathlib import Path

import pandas as pd

from data import db, quality
from data.ingest import load_universe


symbols = list(dict.fromkeys(load_universe()))
parts = []

with closing(
    db.connect_readonly("storage/radar.db")
) as conn:
    conn.execute("BEGIN")

    integrity = conn.execute(
        "PRAGMA quick_check"
    ).fetchall()

    if integrity != [("ok",)]:
        raise RuntimeError(
            f"SQLite không qua quick_check: {integrity}"
        )

    frames = {
        symbol: db.load_ohlc(conn, symbol)
        for symbol in symbols
    }

    for symbol, frame in frames.items():
        summary = db.load_summary(conn, symbol)

        parts.extend([
            quality.check_ohlc(frame, symbol),

            quality.check_cross(
                frame, summary, symbol
            ),

            quality.check_freshness(
                None if frame.empty
                else frame.index.max(),
                symbol=symbol,
            ),
        ])

    parts.append(
        quality.check_calendar(frames)
    )

issues = pd.concat(parts, ignore_index=True)

Path("report").mkdir(exist_ok=True)

issues.to_csv(
    "report/data_quality.csv",
    index=False,
    encoding="utf-8-sig",
)

print("SQLite quick_check: OK")
print("Số mã:", len(symbols))
print(
    "Số dòng OHLC:",
    sum(len(frame) for frame in frames.values()),
)

if issues.empty:
    print("Chưa phát hiện vấn đề trong các kiểm tra đã chạy.")
else:
    print(
        issues.groupby(
            ["check", "severity"]
        ).size().to_string()
    )

print("Đã lưu: report/data_quality.csv")