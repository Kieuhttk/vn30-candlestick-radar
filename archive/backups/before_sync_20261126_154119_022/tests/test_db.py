"""Kiểm tra trực tiếp khóa dữ liệu, NULL, lọc truy vấn và rollback SQLite."""
from contextlib import closing
from datetime import datetime,date
import sqlite3

import numpy as np
import pandas as pd
import pytest

from data import db


def bars():
    return pd.DataFrame({'open':[100.,101.],'high':[103.,104.],'low':[98.,99.],
        'close':[102.,103.],'volume':[1000.,1100.]},index=pd.to_datetime(['2026-01-05','2026-01-06']))


@pytest.fixture
def conn():
    with closing(db.connect(':memory:')) as connection:yield connection


def test_upsert_is_idempotent_and_loader_sorts_and_filters_inclusive_dates(conn):
    frame=bars();db.upsert_ohlc(conn,'FPT',frame.iloc[::-1]);db.upsert_ohlc(conn,'FPT',frame)
    replacement=frame.iloc[:1].copy();replacement['volume']=2000
    db.upsert_ohlc(conn,'FPT',replacement)
    assert conn.execute('SELECT COUNT(*) FROM ohlc_daily').fetchone()[0]==2
    result=db.load_ohlc(conn,'FPT',start='2026-01-05',end='2026-01-05')
    assert len(result)==1 and result.volume.iloc[0]==2000
    assert db.load_ohlc(conn,'FPT').index.is_monotonic_increasing


def test_nan_is_sql_null_and_foreign_flow_join_uses_symbol_and_date(conn):
    frame=bars();frame.loc[frame.index[0],'volume']=np.nan
    db.upsert_ohlc(conn,'FPT',frame);db.upsert_ohlc(conn,'ACB',frame)
    summary=pd.DataFrame({'total_foreign_buy_value':[123.]},index=frame.index[1:])
    db.upsert_summary(conn,'FPT',summary)
    assert conn.execute('SELECT volume FROM ohlc_daily WHERE symbol=? ORDER BY trading_date',('FPT',)).fetchone()[0] is None
    result=db.load_ohlc(conn,'FPT')
    assert np.isnan(result.volume.iloc[0]) and result.total_foreign_buy_value.iloc[1]==123
    assert np.isnan(result.total_foreign_buy_value.iloc[0])
    assert db.load_ohlc(conn,'ACB').total_foreign_buy_value.isna().all()


def test_bound_symbol_values_do_not_turn_into_sql_expressions(conn):
    db.upsert_ohlc(conn,'FPT',bars())
    assert db.load_ohlc(conn,"FPT' OR 1=1 --").empty
    assert db.list_symbols(conn)==['FPT']


def test_failed_multi_table_replacement_rolls_back_prices_summary_and_issues(conn):
    frame=bars();db.upsert_ohlc(conn,'FPT',frame)
    db.upsert_summary(conn,'FPT',pd.DataFrame({'total_match':[1000.,1100.]},index=frame.index))
    issues=pd.DataFrame([dict(symbol='FPT',trading_date='2026-01-05',check='example',severity='warning',detail='giữ vết')])
    db.log_issues(conn,issues)
    before=[db.load_ohlc(conn,'FPT'),db.load_summary(conn,'FPT'),db.read_issues(conn)]
    with pytest.raises(RuntimeError):
        with db.session(conn):
            db.delete_symbol(conn,'FPT',commit=False)
            db.upsert_ohlc(conn,'FPT',frame*2,commit=False)
            raise RuntimeError('simulated failure before committing replacement')
    for expected,actual in zip(before,[db.load_ohlc(conn,'FPT'),db.load_summary(conn,'FPT'),db.read_issues(conn)]):
        pd.testing.assert_frame_equal(expected,actual)


def test_readonly_uri_handles_vietnamese_spaces_and_hash_without_creating_files(tmp_path):
    path=tmp_path/'Đồ án #1'/'radar.db'
    with closing(db.connect(path)) as connection:db.upsert_ohlc(connection,'FPT',bars())
    with closing(db.connect_readonly(path)) as connection:
        assert len(db.load_ohlc(connection,'FPT'))==2
        with pytest.raises(sqlite3.OperationalError):connection.execute('DELETE FROM ohlc_daily')
    missing=path.with_name('missing.db')
    with pytest.raises(FileNotFoundError):db.connect_readonly(missing)
    assert not missing.exists()


def test_issue_upsert_and_date_deletion_preserve_other_symbols(conn):
    rows=[dict(symbol=s,trading_date=d,check='sample',severity='warning',detail='trước')
        for s in ['FPT','ACB'] for d in ['2026-01-05','2026-01-06']]
    db.log_issues(conn,pd.DataFrame(rows))
    changed=pd.DataFrame([dict(rows[0],severity='error',detail='đã đối chiếu')]);db.log_issues(conn,changed)
    assert len(db.read_issues(conn))==4
    assert db.read_issues(conn,symbols=['FPT']).iloc[0].severity=='error'
    db.delete_issues(conn,'FPT',from_date='2026-01-06')
    result=db.read_issues(conn)
    assert len(result[result.symbol=='ACB'])==2 and len(result[result.symbol=='FPT'])==1


def test_status_uses_latest_ingest_and_staleness_from_stored_last_date(conn):
    db.upsert_ohlc(conn,'FPT',bars())
    db.log_ingest(conn,'FPT','failed',now=datetime(2026,1,6,16,tzinfo=db.VN))
    db.log_ingest(conn,'FPT','ok',now=datetime(2026,1,7,16,tzinfo=db.VN))
    status=db.data_status(conn,today=date(2026,1,10)).iloc[0]
    assert status.n_rows==2 and status.days_stale==4 and status.last_status=='ok'
