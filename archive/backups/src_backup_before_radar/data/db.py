"""Lưu trữ SQLite: tạo schema, upsert theo khóa (symbol, trading_date), đọc dữ liệu, nhật ký nạp.

Đường dẫn CSDL lấy từ biến môi trường RADAR_DB_PATH (mặc định storage/radar.db).
Ngày lưu dạng chuỗi ISO 'YYYY-MM-DD' (sắp xếp chữ cái trùng thứ tự thời gian).
Lớp này chỉ lưu và đọc, không chứa logic kiểm tra chất lượng (xem quality.py).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pandas as pd

DEFAULT_DB = "storage/radar.db"
VN = timezone(timedelta(hours=7))

OHLC_COLS = ["open", "high", "low", "close", "volume", "value"]
SUMMARY_COLS = [
    "price_change", "price_change_percentage", "open", "high", "low", "close", "average",
    "total_match", "total_match_value", "total_buy", "total_trade_buy", "total_sell", "total_trade_sell",
    "total_foreign_buy", "total_foreign_buy_value", "total_foreign_sell", "total_foreign_sell_value",
    "remain_foreign_room", "total_foreign_room", "total_deal", "total_deal_value",
]


def _ddl() -> str:
    ohlc = ",\n    ".join(f"{c} REAL" for c in OHLC_COLS)
    summ = ",\n    ".join(f"{c} REAL" for c in SUMMARY_COLS)
    return f"""
CREATE TABLE IF NOT EXISTS ohlc_daily (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    {ohlc},
    PRIMARY KEY (symbol, trading_date)
);
CREATE TABLE IF NOT EXISTS summary_daily (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    {summ},
    PRIMARY KEY (symbol, trading_date)
);
CREATE TABLE IF NOT EXISTS quality_issues (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    check_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    detail TEXT,
    run_at TEXT NOT NULL,
    PRIMARY KEY (symbol, trading_date, check_name)
);
CREATE TABLE IF NOT EXISTS ingest_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    d_from TEXT,
    d_to TEXT,
    n_ohlc INTEGER,
    n_summary INTEGER,
    n_open_dropped INTEGER,
    n_errors INTEGER,
    n_warnings INTEGER,
    status TEXT NOT NULL,
    message TEXT
);
"""


def connect(path=None) -> sqlite3.Connection:
    """Mở (và tạo nếu chưa có) cơ sở dữ liệu, bảo đảm schema đã tồn tại."""
    path = str(path or os.environ.get("RADAR_DB_PATH") or DEFAULT_DB)
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_ddl())


@contextmanager
def session(conn: sqlite3.Connection):
    """Giao dịch nguyên tử: thành công thì commit, có lỗi thì rollback toàn bộ."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _upsert(conn, table, symbol, df, cols, commit):
    if df.empty:
        return 0
    dates = pd.to_datetime(df.index).strftime("%Y-%m-%d")
    body = df.reindex(columns=cols).astype(float)
    obj = body.astype(object).where(body.notna(), None)   # NaN -> NULL
    rows = [(symbol, d, *vals) for d, vals in zip(dates, obj.itertuples(index=False, name=None))]
    placeholders = ", ".join("?" * (len(cols) + 2))
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols)
    conn.executemany(
        f"INSERT INTO {table} (symbol, trading_date, {', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(symbol, trading_date) DO UPDATE SET {updates}",
        rows,
    )
    if commit:
        conn.commit()
    return len(rows)


def upsert_ohlc(conn, symbol: str, df: pd.DataFrame, commit: bool = True) -> int:
    """df: chỉ số là ngày, các cột OHLC_COLS. Trả về số dòng đã ghi (chèn mới hoặc cập nhật)."""
    return _upsert(conn, "ohlc_daily", symbol, df, OHLC_COLS, commit)


def upsert_summary(conn, symbol: str, df: pd.DataFrame, commit: bool = True) -> int:
    return _upsert(conn, "summary_daily", symbol, df, SUMMARY_COLS, commit)


def delete_symbol(conn, symbol: str, commit: bool = True) -> None:
    """Xóa toàn bộ dữ liệu của một mã (dùng khi nạp lại từ đầu). Không xóa nhật ký."""
    conn.execute("DELETE FROM ohlc_daily WHERE symbol = ?", (symbol,))
    conn.execute("DELETE FROM summary_daily WHERE symbol = ?", (symbol,))
    conn.execute("DELETE FROM quality_issues WHERE symbol = ?", (symbol,))
    if commit:
        conn.commit()


def list_symbols(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM ohlc_daily ORDER BY symbol")]


def last_date(conn, symbol: str):
    """Ngày giao dịch mới nhất đã lưu của mã (pd.Timestamp) hoặc None."""
    row = conn.execute("SELECT MAX(trading_date) FROM ohlc_daily WHERE symbol = ?", (symbol,)).fetchone()
    return pd.Timestamp(row[0]) if row and row[0] else None


def _bounds(start, end):
    where, params = [], []
    if start is not None:
        where.append("o.trading_date >= ?")
        params.append(pd.Timestamp(start).strftime("%Y-%m-%d"))
    if end is not None:
        where.append("o.trading_date <= ?")
        params.append(pd.Timestamp(end).strftime("%Y-%m-%d"))
    return where, params


_LOAD_COLS = OHLC_COLS + [
    "total_foreign_buy", "total_foreign_sell",
    "total_foreign_buy_value", "total_foreign_sell_value", "remain_foreign_room",
]


def load_ohlc(conn, symbol: str, start=None, end=None) -> pd.DataFrame:
    """Nến ngày của một mã, **sắp xếp tăng dần**, chỉ số DatetimeIndex tên 'trading_date'.

    Cột: open, high, low, close, volume, value và vài cột dòng tiền nước ngoài.
    LƯU Ý: giá OHLC do SSI trả là giá ĐÃ ĐIỀU CHỈNH ngược về hiện tại (cổ tức tiền và cổ phiếu), nên liên tục
    qua ngày đi quyền; giá trị lưu phụ thuộc thời điểm nạp (xem docs/api_notes.md). price_change của
    securitiesSummary là giá THÔ nên không dùng để suy ra giá tham chiếu cùng thang với close.
    """
    where, params = _bounds(start, end)
    sql = (
        "SELECT o.trading_date, o.open, o.high, o.low, o.close, o.volume, o.value, "
        "s.total_foreign_buy, s.total_foreign_sell, "
        "s.total_foreign_buy_value, s.total_foreign_sell_value, s.remain_foreign_room "
        "FROM ohlc_daily o LEFT JOIN summary_daily s "
        "ON s.symbol = o.symbol AND s.trading_date = o.trading_date "
        "WHERE o.symbol = ? " + "".join(f"AND {w} " for w in where) + "ORDER BY o.trading_date"
    )
    df = pd.read_sql_query(sql, conn, params=[symbol, *params])
    idx = pd.DatetimeIndex(pd.to_datetime(df.pop("trading_date")), name="trading_date")
    df.index = idx
    return df.reindex(columns=_LOAD_COLS).astype(float)   # cột toàn NULL về NaN thay vì object


def load_summary(conn, symbol: str, start=None, end=None) -> pd.DataFrame:
    """Tổng hợp giao dịch theo ngày của một mã (sắp xếp tăng dần, cột SUMMARY_COLS dạng số thực)."""
    where, params = [], []
    if start is not None:
        where.append("AND trading_date >= ?")
        params.append(pd.Timestamp(start).strftime("%Y-%m-%d"))
    if end is not None:
        where.append("AND trading_date <= ?")
        params.append(pd.Timestamp(end).strftime("%Y-%m-%d"))
    sql = (f"SELECT trading_date, {', '.join(SUMMARY_COLS)} FROM summary_daily WHERE symbol = ? "
           + " ".join(where) + " ORDER BY trading_date")
    df = pd.read_sql_query(sql, conn, params=[symbol, *params])
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("trading_date")), name="trading_date")
    return df.reindex(columns=SUMMARY_COLS).astype(float)


# ---------------------------------------------------------------- vấn đề chất lượng (truy vết dòng bị loại)
def delete_issues(conn, symbol: str, from_date=None, commit: bool = True) -> None:
    """Xóa vấn đề đã ghi của mã (từ from_date trở đi nếu có) trước khi ghi lại kết quả kiểm tra mới."""
    if from_date is None:
        conn.execute("DELETE FROM quality_issues WHERE symbol = ?", (symbol,))
    else:
        conn.execute("DELETE FROM quality_issues WHERE symbol = ? AND trading_date >= ?",
                     (symbol, pd.Timestamp(from_date).strftime("%Y-%m-%d")))
    if commit:
        conn.commit()


def log_issues(conn, issues: pd.DataFrame, now=None, commit: bool = True) -> int:
    """Ghi bảng vấn đề (cột symbol, trading_date, check, severity, detail), cập nhật nếu trùng khóa."""
    if issues.empty:
        return 0
    run_at = (now or datetime.now(VN)).strftime("%Y-%m-%d %H:%M:%S")
    rows = [(r.symbol, r.trading_date, r.check, r.severity, r.detail, run_at) for r in issues.itertuples(index=False)]
    conn.executemany(
        "INSERT INTO quality_issues (symbol, trading_date, check_name, severity, detail, run_at) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(symbol, trading_date, check_name) DO UPDATE SET "
        "severity = excluded.severity, detail = excluded.detail, run_at = excluded.run_at", rows)
    if commit:
        conn.commit()
    return len(rows)


def read_issues(conn, symbols=None, check: str | None = None, limit: int = 1000) -> pd.DataFrame:
    """Đọc các vấn đề đã ghi, lọc theo danh sách mã và/hoặc loại kiểm tra."""
    where, params = [], []
    if symbols:
        where.append("symbol IN (" + ",".join("?" * len(symbols)) + ")")
        params += list(symbols)
    if check:
        where.append("check_name = ?")
        params.append(check)
    sql = ("SELECT symbol, trading_date, check_name AS \"check\", severity, detail, run_at FROM quality_issues "
           + ("WHERE " + " AND ".join(where) + " " if where else "")
           + "ORDER BY symbol, trading_date LIMIT ?")
    return pd.read_sql_query(sql, conn, params=params + [limit])


# ---------------------------------------------------------------- nhật ký nạp và trạng thái
def log_ingest(conn, symbol: str, status: str, d_from=None, d_to=None, n_ohlc=0, n_summary=0,
               n_open_dropped=0, n_errors=0, n_warnings=0, message: str = "", now=None) -> None:
    now = now or datetime.now(VN)
    conn.execute(
        "INSERT INTO ingest_log (run_at, symbol, d_from, d_to, n_ohlc, n_summary, n_open_dropped, "
        "n_errors, n_warnings, status, message) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (now.strftime("%Y-%m-%d %H:%M:%S"), symbol,
         None if d_from is None else pd.Timestamp(d_from).strftime("%Y-%m-%d"),
         None if d_to is None else pd.Timestamp(d_to).strftime("%Y-%m-%d"),
         int(n_ohlc), int(n_summary), int(n_open_dropped), int(n_errors), int(n_warnings), status, message),
    )
    conn.commit()


def read_log(conn, limit: int = 50) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM ingest_log ORDER BY id DESC LIMIT ?", conn, params=[limit])


def data_status(conn, today: date | None = None) -> pd.DataFrame:
    """Mỗi mã một dòng: ngày đầu/cuối, số dòng, lần nạp gần nhất, trạng thái và số ngày dữ liệu bị cũ.
    Dùng cho khu 'trạng thái dữ liệu' của giao diện."""
    today = pd.Timestamp(today or datetime.now(VN).date())
    agg = pd.read_sql_query(
        "SELECT symbol, MIN(trading_date) AS first_date, MAX(trading_date) AS last_date, COUNT(*) AS n_rows "
        "FROM ohlc_daily GROUP BY symbol", conn)
    last_run = pd.read_sql_query(
        "SELECT symbol, run_at AS last_run_at, status AS last_status FROM ingest_log "
        "WHERE id IN (SELECT MAX(id) FROM ingest_log GROUP BY symbol)", conn)
    out = agg.merge(last_run, on="symbol", how="outer").sort_values("symbol").reset_index(drop=True)
    out["days_stale"] = (today - pd.to_datetime(out["last_date"])).dt.days
    return out
