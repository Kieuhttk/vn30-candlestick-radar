import numpy as np
import pandas as pd
import pytest
from analytics.event_study import event_outcomes
from analytics.multiple_testing import fdr_by
from finance.indicators import indicators
from analytics.radar import build_radar
from finance.context import signal_context
from analytics.inference import block_test
from analytics.study import q1_tables, q2_tables


def fixture():
    dates=pd.bdate_range('2025-01-01',periods=90)
    f=pd.DataFrame(dict(open=100.,high=103.,low=97.,close=100.,volume=1000.),index=dates)
    f.loc[dates[61],['open','high','low','close']]=[100,110,90,105]
    f.loc[dates[62],['open','high','low','close']]=[105,122,101,120]
    f.loc[dates[63],['open','high','low','close']]=[120,125,80,110]
    e=pd.DataFrame([dict(symbol='FPT',date=dates[60],name='hammer',name_vi='Búa',kind='pattern',bias='bullish')])
    return f,e


def test_hand_calculated_three_session_path():
    f,e=fixture();r=event_outcomes({'FPT':f},e,f.index[-1],horizons=(3,),fee_bps=40).iloc[0]
    assert r.status=='evaluated'
    assert r.gross==pytest.approx(.10)
    assert r.net==pytest.approx(110*.998/(100*1.002)-1)
    assert r.mae==pytest.approx(-.20)
    assert r.entry_date==f.index[61] and r.exit_date==f.index[63]


@pytest.mark.parametrize('case,expected',[('pending','pending'),('missing','missing'),('invalid','invalid'),('issue','invalid')])
def test_statuses(case,expected):
    f,e=fixture();reference=f.copy();asof=f.index[-1];issues=None
    if case=='pending':asof=f.index[62]
    if case=='missing':f=f.drop(f.index[62])
    if case=='invalid':f.loc[f.index[62],'high']=1
    if case=='issue':issues=pd.DataFrame([dict(symbol='FPT',trading_date=f.index[62],severity='error')])
    r=event_outcomes({'FPT':f,'REF':reference},e,asof,issues,horizons=(3,)).iloc[0]
    assert r.status==expected and pd.isna(r.net)


def test_future_prices_events_and_errors_cannot_change_closed_results():
    f,e=fixture();cut=f.index[70]
    a=event_outcomes({'FPT':f},e,cut,horizons=(1,3,5,10,20))
    future=f.copy();future.loc[future.index>cut,['open','high','low','close']]=[10000,11000,9000,10500]
    extra=e.copy();extra['date']=f.index[80]
    future_issues=pd.DataFrame([dict(symbol='FPT',trading_date=f.index[80],severity='error')])
    b=event_outcomes({'FPT':future},pd.concat([e,extra]),cut,issues=future_issues,horizons=(1,3,5,10,20))
    pd.testing.assert_frame_equal(a,b)


def test_directional_bearish_is_signed_contrast_not_short_profit():
    f,e=fixture();e['name']='hanging_man';e['bias']='bearish'
    r=event_outcomes({'FPT':f},e,f.index[-1],horizons=(3,)).iloc[0]
    assert r.oriented_excess==pytest.approx(-r.excess)
    assert r.direction_hit==0 and r.gross>0


def test_known_by_vector_nan_and_fixed_family():
    p=np.array([.01,.04,.03,np.nan]);result=fdr_by(p)
    np.testing.assert_allclose(result[:3],[.055,.07333333333333333,.07333333333333333])
    assert np.isnan(result[3])
    assert np.all(fdr_by(p,n_tests=10)[:3]>=result[:3])
    assert np.isnan(fdr_by([np.nan])[0])
    with pytest.raises(ValueError):fdr_by([1.1])


def test_conditional_baseline_and_indicators_no_future():
    rng=np.random.default_rng(13);dates=pd.bdate_range('2025-01-01',periods=150)
    close=100*np.exp(np.cumsum(rng.normal(0,.01,len(dates))))
    f=pd.DataFrame(dict(open=np.r_[100,close[:-1]],close=close,volume=1000.),index=dates)
    f['high']=f[['open','close']].max(axis=1)*1.01;f['low']=f[['open','close']].min(axis=1)*.99
    e=pd.DataFrame([dict(symbol='FPT',date=dates[80],name='hammer',name_vi='Búa',kind='pattern',bias='bullish')])
    r=event_outcomes({'FPT':f},e,dates[-1],horizons=(1,),fee_bps=0).iloc[0]
    t=indicators(f).trend_t.shift(1)
    eligible=np.arange(len(f))>=11
    controls=[]
    for i in range(len(f)-1):
        if eligible[i] and t.iloc[i]<=-1:controls.append(f.close.iloc[i+1]/f.open.iloc[i+1]-1)
    assert r.n_conditional_baseline==len(controls)
    assert r.conditional_baseline_net==pytest.approx(np.mean(controls))
    first=indicators(f.iloc[:81]);changed=f.copy();changed.iloc[81:,changed.columns.get_loc('close')]*=10
    pd.testing.assert_frame_equal(first,indicators(changed).iloc[:81])


def test_radar_rejects_gap_and_quality_error_without_future_leakage():
    f,e=fixture();cut=f.index[70]
    # Nến thân nhỏ này chắc chắn có tín hiệu trung tính khi đủ lịch sử.
    f.loc[:,['open','high','low','close']]=[100,103,97,100]
    broken=f.drop(f.index[60])
    issues=pd.DataFrame([dict(symbol='FPT',trading_date=f.index[70],severity='error')])
    result=build_radar({'FPT':broken,'REF':f},cut,issues)
    chosen=result.events[result.events.symbol=='FPT']
    assert not chosen[chosen.date.between(f.index[61],cut)].shape[0]
    assert len(result.missing_sessions)==1
    assert result.latest.set_index('symbol').loc['FPT','status']=='Nến bị lỗi chất lượng'
    changed=f.copy();changed.loc[changed.index>cut,['open','high','low','close']]*=10
    pd.testing.assert_frame_equal(build_radar({'REF':f},cut).events,build_radar({'REF':changed},cut).events)


def test_context_exact_next_session_and_past_indicators():
    f,e=fixture();event=e.iloc[0].to_dict();day=event['date'];nxt=f.index[61]
    initial=signal_context(f,event,day,f.index)
    assert initial['status']=='Chờ xác nhận'
    later=f.copy();later.loc[nxt,['open','high','low','close']]=[100,110,99,109]
    result=signal_context(later,event,nxt,f.index)
    assert result['status']=='Đã xác nhận'
    assert result['ema20']==initial['ema20']
    assert result['volume_ratio']==initial['volume_ratio']
    missing=signal_context(later.drop(nxt),event,f.index[62],f.index)
    assert missing['status']=='Thiếu nến xác nhận'


def test_bootstrap_keeps_no_signal_dates_and_is_reproducible():
    calendar=pd.bdate_range('2025-01-01',periods=240)
    signal=pd.Series(np.random.default_rng(31).normal(.001,.01,30),index=calendar[::8])
    dense=signal.reindex(calendar)
    implicit=block_test(signal,calendar,block_size=10,resamples=199,seed=44)
    explicit=block_test(dense,block_size=10,resamples=199,seed=44)
    assert implicit==explicit
    assert implicit['n_dates']==30
    assert implicit['mean']==pytest.approx(signal.mean())
    assert block_test(signal.iloc[:19],calendar,resamples=199)['n_dates']==19
    assert np.isnan(block_test(signal.iloc[:19],calendar,resamples=199)['p'])


def test_fixed_study_family_and_q1_include_absent_patterns():
    f,e=fixture();e['name_vi']='Búa (Hammer)'
    year,symbol=q1_tables(e)
    assert year.shape[0]==19 and symbol.shape[0]==19
    assert year.to_numpy().sum()==symbol.to_numpy().sum()==1
    table,details,family=q2_tables({'FPT':f},e,f.index[-1],resamples=99)
    assert family==280 and len(table)==19*5*2
    assert len(details)==10
    assert table[['all_q_fixed','trend_q_fixed']].isna().all().all()


def test_oos_baseline_ignores_holdout_and_purges_crossing_windows():
    from analytics.event_study import fit_event_baselines
    f,e=fixture();cut=f.index[60]
    model=fit_event_baselines({'FPT':f},cut,horizons=(3,),fee_bps=0)
    hammer=model[model.name=='hammer'].iloc[0]
    assert hammer.n_baseline==47  # vị trí 11..57; giá thoát không vượt vị trí 60
    assert hammer.baseline_net==pytest.approx(0)
    changed=f.copy();changed.loc[changed.index>cut,['open','high','low','close']]=[500.,700.,450.,600.]
    other=fit_event_baselines({'FPT':changed},cut,horizons=(3,),fee_bps=0)
    pd.testing.assert_frame_equal(model,other)
    e['date']=f.index[61]
    result=event_outcomes({'FPT':f},e,f.index[-1],horizons=(3,),fee_bps=0,baselines=model)
    assert result.baseline_fit_end.iloc[0]==cut
    assert result.baseline_net.iloc[0]==0
    assert result.status.iloc[0]=='evaluated'
    leaking=model.copy();leaking['fit_end']=f.index[61]
    with pytest.raises(ValueError,match='TRƯỚC'):
        event_outcomes({'FPT':f},e,f.index[-1],horizons=(3,),fee_bps=0,baselines=leaking)
    wrong=model.copy();wrong['thresholds_hash']='different'
    with pytest.raises(ValueError,match='Ngưỡng'):
        event_outcomes({'FPT':f},e,f.index[-1],horizons=(3,),fee_bps=0,baselines=wrong)


def test_oos_pipeline_warmup_train_purge_and_fixed_family():
    from analytics.study import make_oos_protocol,oos_tables
    f,_=fixture();f.loc[:,['open','high','low','close']]=[100.,103.,97.,100.]
    frames={'FPT':f,'REF':f.copy()}
    protocol,days=make_oos_protocol(frames,f.index[-1])
    assert protocol['n_train_sessions']==63
    assert protocol['train_end']==str(f.index[62].date())
    tables=oos_tables(frames,f.index[-1],None,protocol,resamples=99)
    hold=tables['signals_oos.csv'];cut=pd.Timestamp(protocol['train_end'])
    assert hold.date.min()==f.index[63]  # warmup từ train được phép
    assert (hold.date>cut).all()
    train=tables['q2_train_outcomes.csv']
    assert (train.loc[train.status=='evaluated','exit_date']<=cut).all()
    assert train.purged_boundary.any()
    assert train.loc[train.purged_boundary,'net'].isna().all()
    assert tables['q2_train_summary.csv'][['all_p','trend_p']].isna().all().all()
    assert len(tables['q2_oos_summary.csv'])==190
    assert protocol['primary_family']==280
    assert tables['q2_oos_outcomes.csv'].date.gt(cut).all()


def test_future_only_asset_and_errors_cannot_fit_a_training_baseline():
    from analytics.event_study import fit_event_baselines,summarize_events
    from analytics.study import make_oos_protocol,training_fingerprint
    f,e=fixture();cut=f.index[62];future=f.iloc[70:].copy()
    frames={'FPT':f,'NEW':future}
    protocol,calendar=make_oos_protocol(frames,f.index[-1],train_end=cut)
    assert protocol['calendar_reference_symbols']==['FPT']
    model=fit_event_baselines(frames,cut,horizons=(1,),fee_bps=0,market_days=calendar)
    assert model.loc[model.symbol=='NEW','n_baseline'].eq(0).all()
    e['symbol']='NEW';e['date']=f.index[80]
    outcome=event_outcomes(frames,e,f.index[-1],horizons=(1,),fee_bps=0,baselines=model,market_days=calendar)
    assert outcome.status.iloc[0]=='evaluated' and not outcome.baseline_available.iloc[0]
    assert pd.isna(outcome.excess.iloc[0])
    assert summarize_events(outcome).n_with_baseline.iloc[0]==0
    issues=pd.DataFrame([dict(symbol='FPT',trading_date=f.index[85],severity='error')])
    assert training_fingerprint(frames,None,cut)==training_fingerprint(frames,issues,cut)


def test_q3_frozen_training_probabilities_and_brier_by_hand():
    from analytics.study import q3_oos_tables
    cut=pd.Timestamp('2025-01-31')
    rows=[]
    for name,completed in [('morning_star_setup',2),('evening_star_setup',1)]:
        for i in range(4):
            rows.append(dict(symbol='FPT',setup=name,setup_date=cut-pd.Timedelta(days=10-i),
                next_date=cut-pd.Timedelta(days=9-i),status='completed' if i<completed else 'not_completed'))
    # Có sẵn tương lai trong DB không cho phép đưa nhãn cắt qua ranh giới vào fit.
    rows.append(dict(symbol='FPT',setup='morning_star_setup',setup_date=cut,
                     next_date=cut+pd.Timedelta(days=1),status='completed'))
    train=pd.DataFrame(rows)
    test=pd.DataFrame([dict(symbol='FPT',setup=name,setup_date=cut+pd.Timedelta(days=i+1),
                next_date=cut+pd.Timedelta(days=i+2),status=status) for i,(name,status) in enumerate([
        ('morning_star_setup','completed'),('morning_star_setup','not_completed'),
        ('evening_star_setup','not_completed'),('evening_star_setup','not_completed'),
        ('morning_star_setup','pending'),('evening_star_setup','missing_next_bar')])])
    model,summary,prediction=q3_oos_tables(train,test,cut)
    probs=model.set_index('setup').forecast_probability
    assert probs['morning_star_setup']==pytest.approx(.5)
    assert probs['evening_star_setup']==pytest.approx(1/3)
    overall=summary[summary.setup=='all'].iloc[0]
    assert overall.n_train==8 and overall.n_test_scored==4
    assert overall.n_test_pending==1 and overall.n_test_excluded==1
    assert overall.brier_model==pytest.approx((.25+.25+1/9+1/9)/4)
    assert overall.brier_baseline==pytest.approx((.36+.16+.16+.16)/4)
    assert prediction.loc[~prediction.scored,'brier_model'].isna().all()
    test['status']='completed'
    other,_,_=q3_oos_tables(train,test,cut)
    pd.testing.assert_frame_equal(model,other)


def test_oos_inference_calendar_contains_only_holdout_days(monkeypatch):
    from analytics import study
    from analytics.event_study import fit_event_baselines
    f,e=fixture();cut=f.index[62];e['date']=f.index[65]
    model=fit_event_baselines({'FPT':f},cut,fee_bps=20)
    original=study.summarize_events;seen=[]
    def capture(outcomes,calendar,*args,**kwargs):
        seen.append(calendar)
        return original(outcomes,calendar,*args,**kwargs)
    monkeypatch.setattr(study,'summarize_events',capture)
    study.q2_tables({'FPT':f},e,f.index[-1],fees=(20,),baselines=model,
                    evaluation_start=f.index[63],resamples=99)
    assert len(seen)==1 and seen[0].equals(f.index[63:])


def test_cli_protocol_stays_fixed_when_new_test_data_arrives(tmp_path):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    spec=importlib.util.spec_from_file_location('oos_cli',Path(__file__).parents[1]/'scripts/run_study.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    f,_=fixture();args=SimpleNamespace(train_end=None,train_fraction=None,resamples=99,block_size=20)
    first=cli.locked_protocol(tmp_path,{'FPT':f},None,f.index[-1],args)
    dates=pd.bdate_range(f.index[0],periods=120)
    extended=f.reindex(dates).ffill()
    second=cli.locked_protocol(tmp_path,{'FPT':extended},None,dates[-1],args)
    assert first==second
    changed=extended.copy();changed.iloc[20,changed.columns.get_loc('close')]+=.1
    with pytest.raises(ValueError,match='train đã thay đổi'):
        cli.locked_protocol(tmp_path,{'FPT':changed},None,dates[-1],args)
    args.train_fraction=.8
    with pytest.raises(ValueError,match='Tỷ lệ'):
        cli.locked_protocol(tmp_path,{'FPT':extended},None,dates[-1],args)


def test_circular_block_aggregates_match_literal_resampling():
    from analytics.inference import _block_tables,_draw_totals
    values=np.arange(150,dtype=float).reshape(50,3);values[::4,1]=np.nan
    length=7;starts=np.array([[0,7,14,21,28,35,42,49],[49,1,12,3,18,21,4,31]])
    sums,counts=_draw_totals(_block_tables(values,length),_block_tables(values,1),starts,50,length)
    for row in range(len(starts)):
        indices=((starts[row,:,None]+np.arange(length))%50).reshape(-1)[:50]
        np.testing.assert_allclose(sums[row],np.nansum(values[indices],axis=0))
        np.testing.assert_array_equal(counts[row],np.isfinite(values[indices]).sum(axis=0))


def test_two_sample_inference_includes_training_uncertainty_and_asset_weights():
    from analytics.inference import two_sample_block_test
    rng=np.random.default_rng(51);td=pd.bdate_range('2023-01-01',periods=240);vd=pd.bdate_range('2024-01-01',periods=120)
    values=rng.normal(0,.2,(240,2));values-=values.mean(axis=0);values+=[.01,.03]
    train=pd.DataFrame(values,index=td,columns=['A','B'])
    test=pd.DataFrame({'A':.02,'B':.05},index=vd);test.loc[vd[::2],'B']=np.nan
    result=two_sample_block_test(test,train,resamples=399,block_size=10)
    assert result['mean']==pytest.approx(.0125)
    fixed=pd.DataFrame(np.tile([.01,.03],(240,1)),index=td,columns=['A','B'])
    conditional=two_sample_block_test(test,fixed,resamples=399,block_size=10)
    assert result['high']-result['low'] > conditional['high']-conditional['low']
    reverse=two_sample_block_test(test,train,direction=-1,resamples=399,block_size=10)
    assert reverse['mean']==pytest.approx(-result['mean'])
    with pytest.raises(ValueError,match='tách'):
        two_sample_block_test(test,train.set_axis(vd[0]+pd.to_timedelta(np.arange(240),'D')),resamples=99)


def test_ratio_bootstrap_preserves_label_weights_and_zero_gain():
    from analytics.inference import ratio_block_test
    days=pd.bdate_range('2024-01-01',periods=120)
    count=pd.Series(1.,index=days[:100]);count.iloc[0]=9
    total=pd.Series(0.,index=days[:100]);total.iloc[0]=9
    result=ratio_block_test(total,count,days,resamples=199,block_size=10)
    assert result['mean']==pytest.approx(9/108)
    zero=ratio_block_test(total*0,count,days,resamples=199,block_size=10)
    assert zero['p']==1 and zero['low']==zero['high']==0


def test_inference_withholds_significance_when_fewer_than_ten_blocks():
    from analytics.inference import two_sample_block_test,ratio_block_test
    train=pd.DataFrame({'A':np.zeros(400)},index=pd.bdate_range('2021-01-01',periods=400))
    test=pd.DataFrame({'A':np.full(190,.03)},index=pd.bdate_range('2024-01-01',periods=190))
    result=two_sample_block_test(test,train,block_size=20,resamples=99)
    assert result['mean']==pytest.approx(.03) and np.isnan(result['p'])
    assert np.isnan(result['low']) and result['effective_resamples']==0
    score=ratio_block_test(test.A,pd.Series(1.,index=test.index),block_size=20,resamples=99)
    assert score['mean']==pytest.approx(.03) and np.isnan(score['p'])


def test_training_controls_reproduce_fitted_benchmarks():
    from analytics.event_study import training_control_samples,fit_event_baselines
    f,_=fixture();cut=f.index[65]
    model=fit_event_baselines({'FPT':f},cut,horizons=(1,3,5),fee_bps=40)
    for h in (1,3,5):
        normal,conditional=training_control_samples({'FPT':f},cut,'hammer',h,fee_bps=40)
        row=model[(model.name=='hammer')&model.horizon.eq(h)].iloc[0]
        assert normal.FPT.notna().sum()==row.n_baseline
        assert normal.FPT.mean()==pytest.approx(row.baseline_net)
        assert conditional.FPT.notna().sum()==row.n_conditional_baseline


def test_execution_stress_prices_and_no_assumed_fill():
    from analytics.event_study import execution_stress
    f,e=fixture()
    data=event_outcomes({'FPT':f},e,f.index[-1],horizons=(3,),fee_bps=40).assign(fee_bps=40)
    stress=execution_stress(data,slippages=(0,20))
    row=stress[stress.slippage_bps==20].iloc[0]
    assert row.mean_net_pct==pytest.approx((110*.998*.999/(100*1.002*1.001)-1)*100)
    assert row.mean_mae_pct==pytest.approx((80/(100*1.001)-1)*100)
    assert row.n_execution_eligible==1
    f.loc[f.index[61],['open','high','low','close']]=100.
    data=event_outcomes({'FPT':f},e,f.index[-1],horizons=(3,),fee_bps=40).assign(fee_bps=40)
    no_fill=execution_stress(data).iloc[0]
    assert no_fill.n_execution_eligible==0 and no_fill.n_not_assumed_fill==1
    assert pd.isna(no_fill.mean_net_pct)
