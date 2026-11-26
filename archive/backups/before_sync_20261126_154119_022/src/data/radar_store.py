"""Đọc ảnh chụp nhất quán của SQLite cho giao diện. Không gọi API, không ghi DB."""
from contextlib import closing
from dataclasses import dataclass

import pandas as pd

from data import db


@dataclass
class Snapshot:
    frames: dict[str, pd.DataFrame]
    issues: pd.DataFrame
    logs: pd.DataFrame


def read_snapshot(path, symbols, end=None) -> Snapshot:
    symbols = list(dict.fromkeys(symbols))
    with closing(db.connect_readonly(path)) as conn:
        conn.execute("BEGIN")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"ohlc_daily", "summary_daily", "quality_issues", "ingest_log"}
        if required - tables:
            raise ValueError("SQLite thiếu bảng: " + ", ".join(sorted(required - tables)))
        frames = {symbol: db.load_ohlc(conn, symbol, end=end) for symbol in symbols}
        issue_cols = ["symbol", "trading_date", "check", "severity", "detail", "run_at"]
        log_cols = ["id", "run_at", "symbol", "status", "n_ohlc", "n_errors", "n_warnings", "message"]
        if not symbols:
            return Snapshot(frames, pd.DataFrame(columns=issue_cols), pd.DataFrame(columns=log_cols))
        placeholders = ",".join("?" for _ in symbols)
        issues = pd.read_sql_query(
            'SELECT symbol, trading_date, check_name AS "check", severity, detail, run_at '
            f"FROM quality_issues WHERE symbol IN ({placeholders}) ORDER BY trading_date DESC",
            conn, params=symbols,
        )
        if end is not None:
            issues = issues[pd.to_datetime(issues["trading_date"]) <= pd.Timestamp(end)]
        logs = pd.read_sql_query(
            f"SELECT * FROM ingest_log WHERE symbol IN ({placeholders}) AND id IN "
            "(SELECT MAX(id) FROM ingest_log GROUP BY symbol) ORDER BY symbol",
            conn, params=symbols,
        )
        return Snapshot(frames, issues, logs)
