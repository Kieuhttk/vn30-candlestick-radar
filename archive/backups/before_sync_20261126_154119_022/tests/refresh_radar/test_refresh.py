import pandas as pd
import pytest

from data import db
from data.ingest import ingest_symbol
from ssi_api.client import SSIClient

from refresh_radar.conftest import FakeClient, NOW, candles, summary


def run(conn, client, **kwargs):
    return ingest_symbol(client, conn, "FPT", "2026-09-01", now=NOW, **kwargs)


def assert_preserved(conn, before_ohlc, before_summary):
    pd.testing.assert_frame_equal(db.load_ohlc(conn, "FPT"), before_ohlc)
    pd.testing.assert_frame_equal(db.load_summary(conn, "FPT"), before_summary)


@pytest.mark.parametrize("problem", ["empty", "empty_summary", "missing_first", "missing_middle", "invalid", "infinite", "null_volume", "null_summary", "price_mismatch"])
def test_unsafe_refresh_keeps_both_tables(seeded, problem):
    conn, frame = seeded
    before_o, before_s = db.load_ohlc(conn, "FPT"), db.load_summary(conn, "FPT")
    new = frame.copy(); summ = summary(new)
    if problem == "empty": new = new.iloc[:0]; summ = summ.iloc[:0]
    if problem == "empty_summary": summ = summ.iloc[:0]
    if problem == "missing_first": new = new.iloc[1:]; summ = summ.iloc[1:]
    if problem == "missing_middle": new = new.drop(new.index[1]); summ = summ.drop(summ.index[1])
    if problem == "invalid": new.loc[new.index[1], "high"] = 1
    if problem == "infinite": new.loc[new.index[1], "high"] = float("inf")
    if problem == "null_volume": new.loc[new.index[1], "volume"] = float("nan")
    if problem == "null_summary": summ.loc[summ.index[1], "total_foreign_buy_value"] = float("nan")
    if problem == "price_mismatch": summ["close"] += 1
    result = run(conn, FakeClient(new, summ), full_refresh=True)
    assert result["status"] == "failed"
    assert result["n_ohlc"] == result["n_summary"] == 0
    assert_preserved(conn, before_o, before_s)
    assert db.read_log(conn).iloc[0]["status"] == "failed"


def test_good_refresh_updates_prices_atomically(seeded):
    conn, frame = seeded
    new = frame.copy(); new[["open", "high", "low", "close"]] *= 0.9
    result = run(conn, FakeClient(new), full_refresh=True)
    assert result["status"] == "ok"
    assert len(db.load_ohlc(conn, "FPT")) == len(frame)
    assert db.load_ohlc(conn, "FPT")["close"].tolist() == new["close"].tolist()
    assert db.load_summary(conn, "FPT")["close"].tolist() == new["close"].tolist()


def test_refresh_never_shortens_request_to_later_since(seeded):
    conn, frame = seeded
    api = FakeClient(frame)
    result = ingest_symbol(api, conn, "FPT", "2026-09-03", now=NOW, full_refresh=True)
    assert result["status"] == "ok"
    assert api.calls[0][1] == frame.index.min()


@pytest.mark.parametrize("failing_function", ["upsert_summary", "log_issues"])
def test_failure_after_delete_rolls_back(seeded, monkeypatch, failing_function):
    conn, frame = seeded
    before_o, before_s = db.load_ohlc(conn, "FPT"), db.load_summary(conn, "FPT")
    new = frame.copy(); new[["open", "high", "low", "close"]] *= 0.9
    def fail(*args, **kwargs):
        raise RuntimeError("simulated disk/write failure")
    monkeypatch.setattr(db, failing_function, fail)
    result = run(conn, FakeClient(new), full_refresh=True)
    assert result["status"] == "failed"
    assert result["n_ohlc"] == result["n_summary"] == 0
    assert_preserved(conn, before_o, before_s)


def test_auto_refresh_requests_all_stored_history(seeded):
    conn, frame = seeded
    new = frame.copy(); new[["open", "high", "low", "close"]] *= 0.9
    api = FakeClient(new)
    result = ingest_symbol(api, conn, "FPT", "2026-09-03", now=NOW)
    assert result["status"] == "ok"
    assert [call[1] for call in api.calls if call[0] == "ohlc"] == [pd.Timestamp("2026-09-03"), frame.index.min()]
    assert len(db.load_ohlc(conn, "FPT")) == len(frame)


def test_failed_auto_refresh_preserves_old_scale(seeded):
    conn, frame = seeded
    before_o, before_s = db.load_ohlc(conn, "FPT"), db.load_summary(conn, "FPT")
    new = frame.iloc[1:].copy(); new[["open", "high", "low", "close"]] *= 0.9
    result = ingest_symbol(FakeClient(new), conn, "FPT", "2026-09-03", now=NOW)
    assert result["status"] == "failed"
    assert_preserved(conn, before_o, before_s)


def test_disabled_auto_refresh_does_not_mix_price_scales(seeded):
    conn, frame = seeded
    before_o, before_s = db.load_ohlc(conn, "FPT"), db.load_summary(conn, "FPT")
    new = frame.copy(); new[["open", "high", "low", "close"]] *= 0.9
    result = run(conn, FakeClient(new), auto_refresh=False)
    assert result["status"] == "failed"
    assert_preserved(conn, before_o, before_s)


def test_earlier_since_backfills_existing_symbol(seeded):
    conn, frame = seeded
    # Giữ nguyên cùng thang giá; bổ sung hai phiên cũ trước phần đã có.
    older = frame.iloc[:2].copy(); older.index = pd.bdate_range("2026-08-28", periods=2)
    new = pd.concat([older, frame])
    api = FakeClient(new)
    result = ingest_symbol(api, conn, "FPT", "2026-08-28", now=NOW)
    assert result["status"] == "ok"
    assert api.calls[0][1] == pd.Timestamp("2026-08-28")
    assert len(db.load_ohlc(conn, "FPT")) == 6


def test_summary_older_than_ohlc_is_preserved(seeded):
    conn, frame = seeded
    old = summary(frame.iloc[:1]); old.index = pd.DatetimeIndex(["2026-08-28"])
    db.upsert_summary(conn, "FPT", old)
    api = FakeClient(frame, pd.concat([old, summary(frame)]))
    result = run(conn, api, full_refresh=True)
    assert result["status"] == "ok"
    assert api.calls[0][1] == pd.Timestamp("2026-08-28")
    assert len(db.load_summary(conn, "FPT")) == 5


def test_failed_refresh_keeps_existing_quality_issues(seeded):
    conn, frame = seeded
    old_issue = pd.DataFrame([{"symbol": "FPT", "trading_date": "2026-09-01", "check": "example",
                               "severity": "warning", "detail": "existing issue"}])
    db.log_issues(conn, old_issue, now=NOW)
    before = db.read_issues(conn)
    result = run(conn, FakeClient(frame.iloc[:0]), full_refresh=True)
    assert result["status"] == "failed"
    pd.testing.assert_frame_equal(db.read_issues(conn), before)


def test_refresh_rechecks_rows_added_while_fetching(seeded):
    conn, frame = seeded
    extra = frame.iloc[-1:].copy(); extra.index = pd.DatetimeIndex(["2026-09-07"])
    class ConcurrentClient(FakeClient):
        def securities_summary(self, symbol, start, end, **kwargs):
            # Mô phỏng một tiến trình khác vừa ghi thêm trước khi refresh giữ khóa.
            db.upsert_ohlc(conn, symbol, extra)
            db.upsert_summary(conn, symbol, summary(extra))
            return super().securities_summary(symbol, start, end, **kwargs)
    result = run(conn, ConcurrentClient(frame), full_refresh=True)
    assert result["status"] == "failed"
    assert extra.index[0] in db.load_ohlc(conn, "FPT").index
    assert len(db.load_ohlc(conn, "FPT")) == len(frame) + 1


class Response:
    status_code = 200
    def __init__(self, rows): self.rows = rows
    def json(self): return {"data": self.rows}


@pytest.mark.parametrize("mode", ["repeat", "max_pages"])
def test_incomplete_paging_raises(mode):
    api = object.__new__(SSIClient)
    api.get = lambda path, params: Response([{"n": 1 if mode == "repeat" else params["pageIndex"]}])
    with pytest.raises(RuntimeError, match="lặp lại|chạm max_pages"):
        api._paged("/offline", {}, 1, 2)


def test_complete_paging_stops_at_empty_page():
    api = object.__new__(SSIClient)
    api.get = lambda path, params: Response([{"n": params["pageIndex"]}] if params["pageIndex"] < 3 else [])
    assert api._paged("/offline", {}, 1, 3)["n"].tolist() == [1, 2]


@pytest.mark.parametrize('hour,expected',[ (14,['2026-11-19']), (16,['2026-11-19','2026-11-20']) ])
def test_drop_unclosed_and_future_bars_even_after_close(hour,expected):
    from datetime import datetime
    from data.quality import drop_open_candle,last_closed_day
    f=candles(4);f.index=pd.to_datetime(['2026-11-19','2026-11-20','2026-11-21','2026-11-23'])
    kept,n=drop_open_candle(f,datetime(2026,11,20,hour,tzinfo=db.VN))
    assert kept.index.strftime('%Y-%m-%d').tolist()==expected
    assert n==4-len(expected)
    assert last_closed_day(datetime(2026,11,21,18,tzinfo=db.VN))==pd.Timestamp('2026-11-20')


def test_audit_reports_future_dates_and_infinite_volume(seeded):
    from datetime import datetime
    from data import quality
    from data.ingest import audit_db
    conn,f=seeded
    future=f.iloc[-1:].copy();future.index=pd.to_datetime(['2026-11-23']);db.upsert_ohlc(conn,'FPT',future)
    report=audit_db(conn,now=datetime(2026,11,20,16,tzinfo=db.VN))
    assert 'unclosed_or_future_date' in set(report['check'])
    f.loc[f.index[-1],'volume']=float('inf')
    assert 'non_finite_volume' in set(quality.check_ohlc(f,'FPT')['check'])
    assert quality.check_freshness(pd.NaT,symbol='FPT').iloc[0]['check']=='no_data'


def test_time_guard_understands_utc_timestamps():
    from datetime import datetime,timezone
    from data.quality import drop_open_candle
    f=candles(2);f.index=pd.to_datetime(['2026-11-20T16:00:00Z','2026-11-20T18:00:00Z'])
    kept,n=drop_open_candle(f,datetime(2026,11,20,16,tzinfo=timezone.utc))
    assert len(kept)==1 and n==1
