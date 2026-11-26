from pathlib import Path
from contextlib import closing

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[2] / "src" / "app" / "main.py"


@pytest.fixture
def ui_db(tmp_path):
    """DB mô phỏng riêng cho UI; không cần fixture ở file khác hoặc dữ liệu SSI."""
    from data import db

    path = tmp_path / "radar.db"
    dates = pd.bdate_range("2026-09-01", periods=40)
    opening = pd.Series([100 + i * 0.1 for i in range(40)], index=dates)
    frame = pd.DataFrame({
        "open": opening,
        "high": opening + 1,
        "low": opening - 1,
        "close": opening + 0.01,
        "volume": 1000.0,
        "value": 100000.0,
    }, index=dates)
    with closing(db.connect(path)) as conn:
        for symbol in ("ACB", "FPT"):
            db.upsert_ohlc(conn, symbol, frame)
    return path


def launch(monkeypatch, path):
    monkeypatch.setenv("RADAR_DB_PATH", str(path))
    import requests
    def no_network(*args, **kwargs):
        raise AssertionError("The radar UI must not call HTTP APIs")
    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    return AppTest.from_file(str(APP), default_timeout=30).run()


def test_ui_reads_sqlite_and_filters_without_network(monkeypatch, ui_db):
    app = launch(monkeypatch, ui_db)
    assert not app.exception
    assert len(app.metric) == 4
    assert len(app.tabs) == 0
    assert len(app.get("plotly_chart")) == 4
    assert not any(chart.key == "overview_candles" for chart in app.get("plotly_chart"))
    assert any(chart.key == "scenario_chart" for chart in app.get("plotly_chart"))
    app.button(key="nav_statistics").click().run()
    assert not app.exception
    assert {item.label for item in app.metric} == {
        "Sao mai · tỷ lệ hoàn thành", "Sao hôm · tỷ lệ hoàn thành"}
    app.multiselect(key="symbols").set_value(["FPT"]).run()
    assert not app.exception
    assert app.multiselect(key="symbols").value == ["FPT"]
    app.radio(key="stats_scope").set_value("Theo khoảng hiển thị").run()
    assert not app.exception
    assert next(item for item in app.metric if item.label == "Sao mai · tỷ lệ hoàn thành").value == "—"
    app.button(key="nav_chart").click().run()
    assert not app.exception
    assert app.multiselect(key="symbols").value == ["FPT"]
    assert app.selectbox(key="chart_symbol").value == "FPT"
    assert len(app.get("plotly_chart")) == 1
    app.button(key="nav_radar").click().run()
    assert not app.exception
    assert app.multiselect(key="symbols").value == ["FPT"]
    assert next(item for item in app.metric if item.label == "Mã đủ dữ liệu").value == "1/1"
    app.multiselect(key="symbols").set_value([]).run()
    assert not app.exception
    assert any("Chọn ít nhất" in message.value for message in app.info)


def test_ui_missing_db_does_not_create_one(monkeypatch, tmp_path):
    path = tmp_path / "missing.db"
    app = launch(monkeypatch, path)
    assert not app.exception
    assert len(app.error) == 1
    assert not path.exists()


def test_ui_empty_db_is_clear(monkeypatch, tmp_path):
    from data import db
    path = tmp_path / "empty.db"
    db.connect(path).close()
    app = launch(monkeypatch, path)
    assert not app.exception
    assert any("chưa có nến" in warning.value for warning in app.warning)


def test_ui_historical_day_and_refresh_button(monkeypatch, ui_db):
    from datetime import date
    app = launch(monkeypatch, ui_db)
    app.date_input[0].set_value(date(2026, 9, 10)).run()
    assert not app.exception
    assert app.metric[0].value == "0/30"
    app.button(key="reload_sqlite").click().run()
    assert not app.exception


def test_ui_all_pages_preserve_common_filters(monkeypatch, ui_db):
    from datetime import date
    app = launch(monkeypatch, ui_db)
    app.multiselect(key="symbols").set_value(["FPT"]).run()
    app.date_input[0].set_value(date(2026, 10, 15)).run()
    expected = [("nav_chart", "Mã xem biểu đồ"), ("nav_statistics", "Phạm vi thống kê"),
                ("nav_quality", "Mức độ"), ("nav_method", None), ("nav_radar", "Phạm vi tín hiệu")]
    for key, label in expected:
        app.button(key=key).click().run()
        assert not app.exception
        assert app.date_input[0].value == date(2026, 10, 15)
        assert app.multiselect(key="symbols").value == ["FPT"]
        assert sum('<div class="vr-hero">' in item.value for item in app.markdown) == 1
        if label:
            assert any(item.label == label for item in [*app.selectbox, *app.radio])


def test_page_preferences_survive_navigation_and_removed_symbol(monkeypatch, ui_db):
    app = launch(monkeypatch, ui_db)
    app.button(key="nav_chart").click().run()
    app.selectbox(key="chart_symbol").set_value("FPT").run()
    app.button(key="nav_statistics").click().run()
    app.radio(key="stats_scope").set_value("Theo khoảng hiển thị").run()
    app.button(key="nav_chart").click().run()
    assert not app.exception
    assert app.selectbox(key="chart_symbol").value == "FPT"
    app.multiselect(key="symbols").set_value(["ACB"]).run()
    assert not app.exception
    assert app.selectbox(key="chart_symbol").value == "ACB"
    app.button(key="nav_statistics").click().run()
    assert not app.exception
    assert app.radio(key="stats_scope").value == "Theo khoảng hiển thị"


def test_beginner_reading_and_advanced_tables_are_separate(monkeypatch,ui_db):
    app=launch(monkeypatch,ui_db)
    assert not app.exception
    assert any(e.label == 'Giải thích từ ngữ: nến, xác nhận, EMA và khối lượng' for e in app.expander)
    assert any('1 · NẾN CHO THẤY GÌ' in e.value for e in app.markdown)
    app.checkbox(key='selected_research').check().run()
    assert not app.exception
    assert app.selectbox(key='selected_horizon').value==5
    app.button(key='nav_statistics').click().run()
    assert not app.exception
    assert app.selectbox(key='research_horizon').value==5
    advanced=next(e for e in app.expander if e.label=='Bảng mô tả kỹ thuật và tải CSV')
    assert not advanced.proto.expanded
    app.selectbox(key='research_horizon').set_value(20).run()
    app.number_input(key='event_fee').set_value(40).run()
    assert not app.exception
    assert app.selectbox(key='research_horizon').value==20


def test_oos_panel_reads_frozen_results_and_blocks_future_or_mixed_files(tmp_path,monkeypatch):
    import hashlib,json
    from data import db
    from analytics.study import make_oos_protocol,oos_tables,training_fingerprint
    from contextlib import closing
    import requests
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k: (_ for _ in ()).throw(AssertionError('UI must stay offline')))
    path=tmp_path/'source.db'
    dates=pd.bdate_range('2024-01-01',periods=140)
    frame=pd.DataFrame(dict(open=100.,high=103.,low=97.,close=100.,volume=1000.,value=100000.),index=dates)
    with closing(db.connect(path)) as conn:
        for symbol in ('FPT','ACB'):db.upsert_ohlc(conn,symbol,frame)
        frames={symbol:db.load_ohlc(conn,symbol) for symbol in ('FPT','ACB')}
    end=dates[-1];protocol,_=make_oos_protocol(frames,end)
    tables=oos_tables(frames,end,None,protocol,resamples=99)
    folder=tmp_path/'oos';folder.mkdir()
    protocol_file=folder/'oos_protocol.json';protocol_file.write_text(json.dumps(protocol))
    hashes={}
    for name in ('q2_oos_summary.csv','q3_oos_summary.csv'):
        file=folder/name;tables[name].to_csv(file,index=False)
        hashes[name]=hashlib.sha256(file.read_bytes()).hexdigest()
    manifest=dict(status='complete',mode='oos',asof=str(end.date()),protocol=protocol,
        protocol_sha256=hashlib.sha256(protocol_file.read_bytes()).hexdigest(),table_hashes=hashes,
        input_snapshot_sha256=training_fingerprint(frames,None,end),universe=list(frames))
    (folder/'manifest.json').write_text(json.dumps(manifest))
    script=f'''
from contextlib import closing
import pandas as pd
import streamlit as st
from data import db
from app.signal_workspace import render_oos_results
with closing(db.connect_readonly({str(path)!r})) as conn:
    frames={{symbol:db.load_ohlc(conn,symbol) for symbol in ('FPT','ACB')}}
asof=pd.Timestamp(st.session_state.get('test_asof',{str(end.date())!r}))
render_oos_results(frames,asof,None,folder={str(folder)!r})
'''
    app=AppTest.from_string(script,default_timeout=30).run()
    assert not app.exception
    assert app.selectbox(key='oos_fee').value==20
    app.selectbox(key='oos_pattern').set_value('Doji').run()
    assert not app.exception
    assert any('trung tính' in item.value for item in app.info)
    app.session_state['test_asof']=str(dates[-2].date());app.run()
    assert not app.exception and not app.selectbox
    assert any('sau ngày quét' in item.value for item in app.info)
    with (folder/'q2_oos_summary.csv').open('a') as file:file.write('\n')
    app.session_state['test_asof']=str(end.date());app.run()
    assert not app.exception
    assert any('không khớp manifest' in item.value for item in app.warning)


def test_latest_date_follows_updates_but_keeps_manual_history(monkeypatch,ui_db):
    from data import db
    from data.quality import last_closed_day
    from datetime import date
    from contextlib import closing
    app=launch(monkeypatch,ui_db)
    app.date_input[0].set_value(date(2026,10,15)).run()
    def add(day):
        f=pd.DataFrame(dict(open=105.,high=106.,low=104.,close=105.01,volume=1000.,value=100000.),index=pd.DatetimeIndex([day]))
        with closing(db.connect(ui_db)) as conn:
            for symbol in ('FPT','ACB'):db.upsert_ohlc(conn,symbol,f)
    add('2026-10-27');app.run()
    assert not app.exception and app.date_input[0].value==date(2026,10,15)
    app.button(key='latest_session').click().run()
    assert not app.exception and app.date_input[0].value==date(2026,10,27)
    add('2026-10-28');app.run()
    assert not app.exception and app.date_input[0].value==date(2026,10,28)
    add(last_closed_day()+pd.Timedelta(days=7));app.run()
    assert not app.exception and app.date_input[0].value==date(2026,10,28)
    assert any('nến chưa đóng hoặc tương lai' in item.value for item in app.warning)
