"""Kiểm tra điều phối cập nhật; không gọi SSI hoặc tạo lịch Windows thật."""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util
import sqlite3
import subprocess
import pytest

ROOT=Path(__file__).parents[1]


def load(name,rel):
    spec=importlib.util.spec_from_file_location(name,ROOT/rel)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


update=load('update_schedule_data','scripts/data/update_data.py')
task=load('update_schedule_task','scripts/system/install_update_task.py')


@pytest.mark.parametrize('at,expected',[
    ('2026-11-20T07:59:00+00:00','2026-11-19'),
    ('2026-11-20T08:00:00+00:00','2026-11-20'),
    ('2026-11-21T12:00:00+00:00','2026-11-20'),
    ('2026-11-23T02:00:00+00:00','2026-11-20'),
])
def test_closed_weekday_uses_vietnam_clock(at,expected):
    assert update.closed_weekday(datetime.fromisoformat(at))==expected


def test_status_is_readonly_and_reports_real_db(tmp_path,capsys):
    universe=tmp_path/'src/data/universe_vn30.txt';universe.parent.mkdir(parents=True);universe.write_text('FPT\n')
    db=tmp_path/'storage/radar.db';db.parent.mkdir()
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE ohlc_daily(symbol TEXT,trading_date TEXT)')
        conn.execute("INSERT INTO ohlc_daily VALUES ('FPT','2026-11-18')")
    before=db.read_bytes()
    update.show_status(tmp_path,'storage/radar.db')
    text=capsys.readouterr().out
    assert str(db) in text and '2026-11-18' in text
    assert db.read_bytes()==before
    assert not (tmp_path/'storage/backups').exists()
    assert not (tmp_path/'report').exists()


def test_status_task_does_not_register_or_start():
    def run(command,**kwargs):
        script=command[-1]
        assert script==task.STATUS
        assert 'Register-ScheduledTask' not in script and 'Start-ScheduledTask' not in script
        assert 'scripts\\data\\update_data.py' in script
        return subprocess.CompletedProcess(command,3)
    assert task.main(['--status'],runner=run,platform='nt')==3


def test_register_uses_current_paths_and_passes_arguments_in_environment(tmp_path,monkeypatch):
    root=tmp_path/'Dự án có khoảng trắng';root.mkdir();monkeypatch.setattr(task,'ROOT',root)
    def run(command,**kwargs):
        assert command[-1]==task.POWERSHELL
        env=kwargs['env']
        assert env['VN30_RADAR_TASK_ROOT']==str(root)
        assert env['VN30_RADAR_TASK_RUN_NOW']=='1'
        assert env['VN30_RADAR_TASK_TIME']=='18:00' and env['VN30_RADAR_TASK_RETRY_TIME']=='19:00'
        assert 'scripts\\data\\update_data.py' in command[-1]
        assert 'New-ScheduledTaskTrigger -AtLogOn' in command[-1]
        assert 'StartWhenAvailable' in command[-1]
        return subprocess.CompletedProcess(command,0)
    assert task.main(['--run-now'],runner=run,platform='nt')==0


def test_non_windows_does_not_try_to_register():
    def fail(*a,**kw):pytest.fail('Không được gọi PowerShell trên Linux')
    with pytest.raises(SystemExit):task.main([],runner=fail,platform='posix')
