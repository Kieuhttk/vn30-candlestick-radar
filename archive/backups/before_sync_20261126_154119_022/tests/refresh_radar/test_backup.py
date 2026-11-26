from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup_sqlite.py"


@pytest.mark.parametrize('stdio_encoding',['utf-8','cp1252:strict'])
def test_backup_keeps_data_and_refuses_overwrite(ui_db, tmp_path,stdio_encoding):
    target = tmp_path / "backup.db"
    command = [sys.executable, str(SCRIPT), "--db", str(ui_db), "--out", str(target)]
    child_env={**os.environ,'PYTHONIOENCODING':stdio_encoding,'PYTHONUTF8':'0'}
    result=subprocess.run(command,capture_output=True,encoding='utf-8',env=child_env)
    assert result.returncode == 0,result.stderr
    assert 'Đã sao lưu:' in result.stdout
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ohlc_daily").fetchone()[0] == 80
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert subprocess.run(command,capture_output=True,encoding='utf-8',env=child_env).returncode != 0


@pytest.mark.parametrize('stdio_encoding',['utf-8','cp1252:strict'])
def test_backup_missing_source_does_not_create_empty_database(tmp_path,stdio_encoding):
    source = tmp_path / "absent.db"; target = tmp_path / "backup.db"
    child_env={**os.environ,'PYTHONIOENCODING':stdio_encoding,'PYTHONUTF8':'0'}
    result = subprocess.run([sys.executable, str(SCRIPT), "--db", str(source), "--out", str(target)], capture_output=True,encoding='utf-8',env=child_env)
    assert result.returncode != 0
    assert 'Không có DB nguồn:' in result.stderr
    assert not source.exists()
    assert not target.exists()
