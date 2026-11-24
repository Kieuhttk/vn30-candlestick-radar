from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from data import db

NOW = datetime(2026, 11, 17, 16, tzinfo=db.VN)


def candles(periods=40):
    dates = pd.bdate_range("2026-09-01", periods=periods)
    opening = 100 + np.arange(periods) * 0.1
    return pd.DataFrame({"open": opening, "high": opening + 1, "low": opening - 1,
                         "close": opening + 0.01, "volume": 1000., "value": 100000.}, index=dates)


def summary(frame):
    result = pd.DataFrame(index=frame.index, columns=db.SUMMARY_COLS, dtype=float)
    result[["open", "high", "low", "close"]] = frame[["open", "high", "low", "close"]]
    result["total_match"] = frame["volume"]
    result["total_foreign_buy_value"] = 12345.
    return result


class FakeClient:
    def __init__(self, ohlc, summ=None):
        self.bars = ohlc
        self.summ = summary(ohlc) if summ is None else summ
        self.calls = []

    def _read(self, name, frame, start, end):
        self.calls.append((name, pd.Timestamp(start), pd.Timestamp(end)))
        data = frame.loc[(frame.index >= start) & (frame.index <= end)]
        return data.rename_axis("tradingDate").reset_index()

    def ohlc(self, symbol, start, end, **kwargs):
        return self._read("ohlc", self.bars, start, end)

    def securities_summary(self, symbol, start, end, **kwargs):
        return self._read("summary", self.summ, start, end)


@pytest.fixture
def seeded():
    conn = db.connect(":memory:")
    frame = candles(4)
    db.upsert_ohlc(conn, "FPT", frame)
    db.upsert_summary(conn, "FPT", summary(frame))
    yield conn, frame
    conn.close()


@pytest.fixture
def ui_db(tmp_path):
    path = tmp_path / "radar.db"
    conn = db.connect(path)
    for symbol in ("ACB", "FPT"):
        frame = candles()
        db.upsert_ohlc(conn, symbol, frame)
        db.upsert_summary(conn, symbol, summary(frame))
        db.log_ingest(conn, symbol, "ok", now=NOW)
    conn.close()
    return path
