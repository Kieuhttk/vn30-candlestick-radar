import importlib.util
from contextlib import nullcontext
from pathlib import Path
import numpy as np
import pandas as pd
from analytics.event_study import event_outcomes
from analytics.event_study import summarize_events
from finance.context import signal_context
from finance.patterns import pattern_catalog
from app.signal_workspace import EXPLANATIONS, explain_signal


def bars():
    dates=pd.bdate_range('2026-01-01',periods=90)
    return pd.DataFrame(dict(open=np.full(90,100.),high=np.full(90,112.),low=np.full(90,98.),close=np.full(90,110.),volume=np.full(90,1000.)),index=dates)


def event(f):
    return dict(symbol='FPT',date=f.index[60],name='hammer',name_vi='Búa',bias='bullish',kind='pattern',confirmation='')


def test_entry_cost_and_no_future_leakage():
    f=bars();e=pd.DataFrame([event(f)])
    early=event_outcomes({'FPT':f},e,f.index[63],horizons=(5,))
    assert early.iloc[0].status=='pending'
    full=event_outcomes({'FPT':f},e,f.index[-1],horizons=(5,),fee_bps=20).iloc[0]
    assert full.entry_date==f.index[61] and full.exit_date==f.index[65]
    assert np.isclose(full.gross,.1)
    assert np.isclose(full.net,110*.999/(100*1.001)-1)
    assert np.isclose(full.mae,-.02)


def test_missing_market_session_excluded():
    f=bars();e=pd.DataFrame([event(f)])
    missing=f.drop(f.index[63])
    rows=event_outcomes({'FPT':missing,'ACB':f},e,f.index[-1],horizons=(5,))
    assert rows.iloc[0].status=='missing'


def test_context_uses_signal_date_for_indicators_and_asof_for_confirmation():
    f=bars();e=event(f);early=signal_context(f,e,e['date'],f.index)
    changed=f.copy();changed.loc[changed.index>e['date'],'volume']=1e9
    changed.loc[changed.index>e['date'],'close']=111
    later=signal_context(changed,e,f.index[-1],f.index)
    assert early['status']=='Chờ xác nhận'
    assert early['volume_ratio']==later['volume_ratio']==1
    assert early['ema20']==later['ema20']


def test_cleanup_dry_run_move_and_undo(tmp_path):
    path=Path(__file__).parents[1]/'scripts/maintenance/organize_project.py'
    spec=importlib.util.spec_from_file_location('cleanup',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    (tmp_path/'src').mkdir();(tmp_path/'tests').mkdir();(tmp_path/'storage').mkdir()
    (tmp_path/'storage/radar.db').write_bytes(b'keep')
    utility=tmp_path/'check_data.py';utility.write_text('from pathlib import Path\nROOT=Path(__file__).resolve().parent\nprint(ROOT)\n')
    assert m.plan(tmp_path) and utility.exists()
    manifest=m.apply(tmp_path)
    assert not utility.exists() and (tmp_path/'scripts/data/check_data.py').exists()
    assert (tmp_path/'storage/radar.db').read_bytes()==b'keep'
    m.undo(tmp_path,manifest)
    assert utility.exists()


def test_summary_copy_on_write_does_not_mutate_readonly_input():
    data=pd.DataFrame({'name_vi':['Búa']*40,'horizon':[5]*40,'status':['evaluated']*40,
                       'date':pd.bdate_range('2026-01-01',periods=40),
                       'gross':[.1]*40,'net':[.098]*40,'mae':[-.02]*40,'excess':[1e-17]*40})
    before=data.copy(deep=True)
    with (nullcontext() if int(pd.__version__.split('.')[0])>=3 else pd.option_context('mode.copy_on_write',True)):
        view=data.groupby('date').excess.mean().dropna().to_numpy()
        assert not view.flags.writeable
        result=summarize_events(data)
    pd.testing.assert_frame_equal(data,before)
    assert result['p bootstrap'].iloc[0]==1
    assert result['q BY'].iloc[0]==1
    assert result['Chênh nền TB theo ngày (%)'].iloc[0]==0


def test_summary_copy_on_write_all_pending():
    data=pd.DataFrame({'name_vi':['Búa'],'horizon':[20],'status':['pending'],
                       'date':[pd.Timestamp('2026-11-18')],
                       'gross':[np.nan],'net':[np.nan],'mae':[np.nan],'excess':[np.nan]})
    with (nullcontext() if int(pd.__version__.split('.')[0])>=3 else pd.option_context('mode.copy_on_write',True)):
        result=summarize_events(data)
    assert result['Đủ dữ liệu'].iloc[0]==0
    assert pd.isna(result['p bootstrap'].iloc[0])


def test_every_detected_pattern_has_an_explanation():
    assert set(pattern_catalog().name)==set(EXPLANATIONS)
    row=dict(name='morning_star_setup',bias='bullish',kind='setup',status='Chờ xác nhận',
             follow='Nến thứ ba tăng, đóng cửa trên 105 đồng.',high=110.,low=98.)
    text=explain_signal(row)
    assert 'Chưa đủ ba nến' in text['meaning']
    assert text['condition']==row['follow']
    row.update(name='bearish_engulfing',kind='pattern',bias='bearish',status='Đã xác nhận')
    text=explain_signal(row)
    assert '98,00' in text['condition'] and 'dưới' in text['condition']
    assert 'không đảm bảo' in text['status']


def test_quality_error_prevents_confirmation_even_with_valid_ohlc():
    f=bars();e=event(f);nxt=f.index[61]
    f.loc[nxt,['open','high','low','close']]=[110.,116.,109.,115.]
    assert signal_context(f,e,nxt,f.index)['status']=='Đã xác nhận'
    issues=pd.DataFrame([dict(symbol='FPT',trading_date=nxt,severity='error')])
    result=signal_context(f,e,nxt,f.index,issues)
    assert result['status']=='Nến xác nhận không hợp lệ'
    explained=explain_signal(dict(e,**result))
    assert 'dữ liệu' in explained['status']
    assert 'nạp bù' in explained['action']
    # Lỗi sau ngày quét không thay đổi kết quả ở ngày đang xét.
    issues['trading_date']=f.index[80]
    assert signal_context(f,e,nxt,f.index,issues)['status']=='Đã xác nhận'


def test_context_does_not_bridge_missing_market_sessions():
    f=bars();e=event(f);calendar=f.index
    broken=f.drop(calendar[45])
    result=signal_context(broken,e,e['date'],calendar)
    assert result['context_gaps']==1
    assert pd.isna(result['ema20']) and pd.isna(result['ema50'])
    assert pd.isna(result['support']) and pd.isna(result['volume_ratio'])
    e['date']=calendar[80]
    recovered=signal_context(broken,e,e['date'],calendar)
    assert pd.notna(recovered['ema20']) and pd.isna(recovered['ema50'])


def test_watchlist_atomic_writes_do_not_share_temporary_filename(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import json
    from app.signal_workspace import save_watchlist
    path=tmp_path/'watchlist.json';choices=[['FPT','ACB'],['BID','CTG']]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(save_watchlist,path,choice) for choice in choices]
        for future in futures:future.result()
    assert json.loads(path.read_text()) in choices
    assert not list(tmp_path.glob('*.tmp'))
