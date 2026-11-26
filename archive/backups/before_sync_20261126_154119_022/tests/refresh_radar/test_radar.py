import sqlite3

import pandas as pd
import pytest

from analytics.radar import build_radar
from data import db
from data.radar_store import read_snapshot
from refresh_radar.conftest import candles


def test_readonly_connection_cannot_write_or_create(tmp_path, ui_db):
    conn = db.connect_readonly(ui_db)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM ohlc_daily")
    conn.close()
    absent = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError): db.connect_readonly(absent)
    assert not absent.exists()


def test_snapshot_filters_universe_and_end(ui_db):
    snapshot = read_snapshot(ui_db, ["FPT"], end="2026-09-10")
    assert set(snapshot.frames) == {"FPT"}
    assert snapshot.frames["FPT"].index.max() <= pd.Timestamp("2026-09-10")
    assert set(snapshot.logs["symbol"]) == {"FPT"}


def test_wrong_schema_is_not_automatically_modified(tmp_path):
    path = tmp_path / "wrong.db"
    conn = sqlite3.connect(path); conn.execute("CREATE TABLE unrelated (x TEXT)"); conn.close()
    with pytest.raises(ValueError, match="thiếu bảng"):
        read_snapshot(path, ["FPT"])
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("unrelated",)]
    conn.close()


def test_gap_suppresses_signals_until_window_is_contiguous():
    frame = candles(45)
    broken = frame.drop(frame.index[20])
    result = build_radar({"FPT": broken, "ACB": frame, "BID": frame}, frame.index[-1])
    affected = result.events[result.events["symbol"] == "FPT"]
    assert not affected[affected["date"].between(frame.index[21], frame.index[31])].shape[0]
    assert len(affected[affected["date"] == frame.index[-1]]) > 0
    assert len(result.missing_sessions) == 1


def test_future_rows_do_not_change_historical_radar():
    frame = candles(40); day = frame.index[25]
    base = build_radar({"FPT": frame}, day)
    changed = frame.copy(); changed.loc[changed.index > day, ["open", "high", "low", "close"]] *= 10
    other = build_radar({"FPT": changed}, day)
    pd.testing.assert_frame_equal(base.events, other.events)
    pd.testing.assert_frame_equal(base.latest, other.latest)


def test_stale_symbol_does_not_reuse_old_signal():
    frame = candles(40)
    result = build_radar({"FPT": frame.iloc[:-1], "ACB": frame, "BID": frame}, frame.index[-1])
    row = result.latest.set_index("symbol").loc["FPT"]
    assert row["patterns"] == row["setups"] == ""
    assert row["status"] == "Thiếu nến ngày đang xem"


def test_error_issue_suppresses_retained_old_bar():
    frame = candles(40)
    issues = pd.DataFrame([{"symbol": "FPT", "severity": "error", "trading_date": str(frame.index[-1].date())}])
    result = build_radar({"FPT": frame}, frame.index[-1], issues)
    assert result.latest.iloc[0]["status"] == "Nến bị lỗi chất lượng"
    assert not (result.events["date"] == frame.index[-1]).any()


def test_short_and_empty_histories_are_reported():
    frame = candles(3)
    result = build_radar({"FPT": frame, "ACB": frame.iloc[:0]}, frame.index[-1])
    assert result.events.empty
    assert set(result.latest["status"]) == {"Chưa đủ cửa sổ liên tiếp", "Chưa có dữ liệu"}


def test_invalid_infinite_bar_does_not_crash_or_emit_signal():
    frame = candles(40); frame.loc[frame.index[-1], "high"] = float("inf")
    result = build_radar({"FPT": frame}, frame.index[-1])
    assert result.latest.iloc[0]["status"] == "Nến bị lỗi chất lượng"
