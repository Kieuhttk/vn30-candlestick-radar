import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pandas as pd
import pytest

from data import db
from data.ingest import ingest_many
from refresh_radar.conftest import FakeClient, NOW, candles, summary

SPEC = importlib.util.spec_from_file_location("auto_update", Path(__file__).parents[1] / "scripts/data/update_data.py")
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)


def project(tmp_path):
    universe = tmp_path / "src/data/universe_vn30.txt"
    universe.parent.mkdir(parents=True)
    universe.write_text("# Research universe\nFPT\n", encoding="utf-8")
    path = tmp_path / "storage/radar.db"
    frame = candles(6)
    conn = db.connect(path)
    db.upsert_ohlc(conn, "FPT", frame.iloc[:4])
    db.upsert_summary(conn, "FPT", summary(frame.iloc[:4]))
    conn.close()
    return path, frame


def offline_runner(path, frame):
    def run(command, **kwargs):
        assert "--full-refresh" not in command
        assert command[command.index("--db") + 1] == str(path)
        assert kwargs["cwd"] == str(path.parent.parent)
        assert kwargs["env"]["PYTHONPATH"].split(__import__("os").pathsep)[0] == str(path.parent.parent / "src")
        conn = db.connect(path)
        try:
            result = ingest_many(FakeClient(frame), conn, ["FPT"], "2021-01-01", now=NOW)
            print(result.to_string(index=False), file=kwargs["stdout"], flush=True)
            return subprocess.CompletedProcess(command, int(result.status.ne("ok").any()))
        finally:
            conn.close()
    return run


def test_auto_update_appends_and_snapshot_keeps_previous_data(tmp_path):
    path, frame = project(tmp_path)
    assert update.run_update(tmp_path, "storage/radar.db", offline_runner(path, frame)) == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ohlc_daily").fetchone()[0] == 6
    backups = list((path.parent / "backups").glob("*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ohlc_daily").fetchone()[0] == 4
        assert conn.execute("PRAGMA quick_check").fetchall() == [("ok",)]
    text = next((tmp_path / "report/update_logs").glob("*.log")).read_text(encoding="utf-8")
    assert "FPT" in text and "1/1 mã có ngày cuối tăng" in text


def test_auto_update_exposes_failed_refresh_and_preserves_history(tmp_path):
    path, frame = project(tmp_path)
    revised = frame.iloc[1:].copy()
    revised[["open", "high", "low", "close"]] *= .9
    assert update.run_update(tmp_path, path, offline_runner(path, revised)) == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ohlc_daily").fetchone()[0] == 4
        assert conn.execute("SELECT close FROM ohlc_daily ORDER BY trading_date LIMIT 1").fetchone()[0] == frame.close.iloc[0]
    text = next((tmp_path / "report/update_logs").glob("*.log")).read_text(encoding="utf-8")
    assert "Có lỗi nạp (exit code 1)" in text


def test_auto_update_missing_db_does_not_create_empty_db(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        update.run_update(tmp_path, path)
    assert not path.exists()


def test_overlapping_update_is_blocked_and_lock_is_released(tmp_path):
    path = tmp_path / "update.lock"
    with update.update_lock(path):
        with pytest.raises(RuntimeError, match="cập nhật khác"):
            with update.update_lock(path):
                pytest.fail("An overlapping run must not acquire the lock")
    with update.update_lock(path):
        pass


def test_update_writes_machine_readable_status_and_masks_future_dates(tmp_path):
    import json
    path,frame=project(tmp_path)
    assert update.run_update(tmp_path,path,offline_runner(path,frame))==0
    status=json.loads((tmp_path/'report/update_logs/latest_status.json').read_text(encoding='utf-8'))
    assert status['state']=='finished' and status['returncode']==0
    assert status['latest_closed_dates']['FPT']==str(frame.index[-1].date())
    assert status['advanced_symbols']==1
    future=frame.iloc[-1:].copy();future.index=pd.to_datetime(['2099-01-01'])
    with sqlite3.connect(path) as conn:db.upsert_ohlc(conn,'FPT',future)
    last=update.latest_dates(path,['FPT'],asof='2026-11-20')
    assert last['FPT'][0]==str(frame.index[-1].date())


def test_launch_failure_is_recorded_without_changing_old_prices(tmp_path):
    import json
    path,frame=project(tmp_path)
    def fail(*args,**kwargs):raise OSError('Cannot start child process')
    with pytest.raises(OSError):update.run_update(tmp_path,path,fail)
    status=json.loads((tmp_path/'report/update_logs/latest_status.json').read_text(encoding='utf-8'))
    assert status['state']=='failed' and status['exception_type']=='OSError'
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM ohlc_daily').fetchone()[0]==4


def test_status_cli_preserves_vietnamese_with_cp1252_pipe(tmp_path):
    path,_=project(tmp_path/'Đồ án KIEU')
    before=path.read_bytes()
    env={**os.environ,'PYTHONIOENCODING':'cp1252:strict','PYTHONUTF8':'0'}
    result=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'scripts/data/update_data.py'),
        '--db',str(path),'--status'],capture_output=True,encoding='utf-8',env=env)
    assert result.returncode==0,result.stderr
    assert 'SQLite thực sự đang kiểm tra:' in result.stdout
    assert 'chưa gọi SSI hoặc thay đổi DB' in result.stdout
    assert path.read_bytes()==before
