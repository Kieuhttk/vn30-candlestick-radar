"""Xuất Q1–Q3 có cấu hình cố định; không chọn ngưỡng dựa trên kết quả."""
from dataclasses import asdict, replace
import numpy as np
import pandas as pd
from finance.candles import Thresholds
from finance.patterns import pattern_catalog
from analytics.radar import build_radar, infer_market_days
from analytics.event_study import event_outcomes, summarize_events, fit_event_baselines, training_control_samples, execution_stress
from analytics.inference import two_sample_block_test, ratio_block_test
from analytics.setup_probability import build_setup_outcomes, summarize_setups
from analytics.multiple_testing import fdr_by
from analytics.setup_probability import PAIRS, wilson_interval
import hashlib

HORIZONS=(1,3,5,10,20)
FEES=(20,40)


def q1_tables(events):
    patterns=events[events.kind=='pattern'].copy()
    patterns['year']=pd.to_datetime(patterns.date).dt.year
    by_year=pd.crosstab(patterns.name_vi,patterns.year).reindex(pattern_catalog('pattern').name_vi,fill_value=0)
    by_symbol=pd.crosstab(patterns.name_vi,patterns.symbol).reindex(pattern_catalog('pattern').name_vi,fill_value=0)
    return by_year,by_symbol


def q2_tables(frames,events,asof,issues=None,horizons=HORIZONS,fees=FEES,resamples=1000,block_size=20,
              baselines=None,market_days=None,evaluation_start=None,inference=True):
    catalog=pattern_catalog('pattern')
    calendar=(infer_market_days({s:f.loc[f.index<=asof] for s,f in frames.items()}) if market_days is None
              else pd.DatetimeIndex(market_days))
    calendar=calendar[calendar<=pd.Timestamp(asof)]
    evaluation_calendar=calendar
    if evaluation_start is not None:
        events=events[events.date>=pd.Timestamp(evaluation_start)]
        evaluation_calendar=calendar[calendar>=pd.Timestamp(evaluation_start)]
    summaries=[];details=[]
    index=pd.MultiIndex.from_product([catalog.name_vi,horizons],names=['Mẫu hình','Số phiên'])
    for fee in fees:
        outcomes=event_outcomes(frames,events,asof,issues,horizons,fee,baselines=baselines,market_days=calendar)
        result=summarize_events(outcomes,evaluation_calendar,block_size,resamples,inference=inference and baselines is None)
        if baselines is not None and inference and not outcomes.empty:
            fit_dates=pd.to_datetime(baselines.fit_end).drop_duplicates()
            if len(fit_dates)!=1:raise ValueError('Bootstrap train/test yêu cầu một mốc fit chung')
            cut=fit_dates.iloc[0];train_calendar=calendar[calendar<=cut]
            for (label,h),group in outcomes.groupby(['name_vi','horizon']):
                bias=group.bias.iloc[0]
                if bias=='neutral':continue
                direction=1 if bias=='bullish' else -1;name=group['name'].iloc[0]
                good=group[group.status=='evaluated']
                controls=training_control_samples(frames,cut,name,int(h),fee,issues,market_days=train_calendar)
                target=(result['Mẫu hình']==label)&result['Số phiên'].eq(h)
                for kind,column,train_values in [('all','excess',controls[0]),('trend','conditional_excess',controls[1])]:
                    paired=good[good[column].notna()]
                    if paired.duplicated(['date','symbol']).any():raise ValueError('Trùng nhãn cùng mã/ngày/mẫu hình')
                    test_values=paired.pivot(index='date',columns='symbol',values='net')
                    expected=baselines[(baselines.name==name)&baselines.horizon.eq(h)&baselines.fee_bps.eq(fee)].set_index('symbol')
                    expected_column='baseline_net' if kind=='all' else 'conditional_baseline_net'
                    if len(test_values.columns):
                        actual=train_values[test_values.columns].mean()
                        if not np.allclose(actual,expected.loc[actual.index,expected_column],equal_nan=True,rtol=1e-10,atol=1e-12):
                            raise ValueError('Mức nền đã fit không khớp snapshot train dùng để bootstrap')
                    # Cửa sổ chồng lấn tạo phụ thuộc dài h; 2*h bị thiếu phủ trong
                    # chẩn đoán mô phỏng. Dùng 5*h và từ chối khi còn <10 khối.
                    effective_block=max(block_size,5*int(h))
                    test=two_sample_block_test(test_values,train_values, evaluation_calendar,train_calendar,
                                               direction,effective_block,resamples)
                    test['block_size']=effective_block
                    for key,value in test.items():result.loc[target,f'{kind}_{key}']=value
        if result.empty:result=pd.DataFrame(index=index).reset_index()
        else:result=result.set_index(['Mẫu hình','Số phiên']).reindex(index).reset_index()
        result['bias']=result['Mẫu hình'].map(catalog.set_index('name_vi').bias)
        result['fee_bps']=fee
        for col in ['Tổng nhãn','Đủ dữ liệu','Chưa đủ tương lai','Loại thiếu/lỗi']:
            result[col]=result[col].fillna(0).astype(int) if col in result else 0
        for col in ['all_p','trend_p']:
            if col not in result: result[col]=np.nan
        summaries.append(result);details.append(outcomes.assign(fee_bps=fee))
    result=pd.concat(summaries,ignore_index=True)
    # Họ kiểm định được chốt trước, gồm cả nhãn không đủ số quan sát.
    family=int(catalog.bias.ne('neutral').sum())*len(horizons)*len(fees)*2
    combined=np.column_stack([result.all_p,result.trend_p]).reshape(-1)
    q=fdr_by(combined,n_tests=family).reshape(-1,2)
    result['all_q_fixed']=q[:,0];result['trend_q_fixed']=q[:,1]
    return result,pd.concat(details,ignore_index=True),family


def sensitivity_tables(frames,asof,issues=None):
    base=Thresholds();scenarios=[('default',base)]
    for field,values in [('doji_k',(.05,.15)),('trend_t',(.75,1.25)),('avg_window',(20,)),('strict_gap',(True,))]:
        scenarios += [(f'{field}={value}',replace(base,**{field:value})) for value in values]
    counts=[];setups=[]
    for label,th in scenarios:
        radar=build_radar(frames,asof,issues,th=th)
        c=radar.events.groupby(['kind','name']).size().rename('n').reset_index().assign(scenario=label)
        counts.append(c)
        q3=summarize_setups(build_setup_outcomes(frames,asof,issues,th=th)).assign(scenario=label,parameters=str(asdict(th)))
        setups.append(q3)
    return pd.concat(counts,ignore_index=True),pd.concat(setups,ignore_index=True)


def make_oos_protocol(frames,asof,train_fraction=.7,train_end=None,reference_symbols=None,
                      horizons=HORIZONS,fees=FEES):
    """Chia theo phiên thị trường chung; không chia ngẫu nhiên theo mã/nhãn."""
    if not 0 < train_fraction < 1:raise ValueError('train_fraction phải nằm giữa 0 và 1')
    asof=pd.Timestamp(asof).normalize()
    closed={s:f.loc[f.index<=asof].sort_index() for s,f in frames.items()}
    initial=infer_market_days(closed)
    if len(initial)<2:raise ValueError('Không đủ phiên để chia train/test')
    if train_end is None:
        count=int(np.floor(np.nextafter(len(initial)*train_fraction,np.inf)))
        if count<1 or count>=len(initial):raise ValueError('Tỷ lệ chia tạo tập rỗng')
        cut=initial[count-1]
    else:cut=pd.Timestamp(train_end).normalize()
    known=[s for s,f in closed.items() if not f.loc[f.index<=cut].empty]
    reference=list(reference_symbols) if reference_symbols is not None else sorted(known)
    if not reference or not set(reference).issubset(known):
        raise ValueError('Rổ suy lịch phải có dữ liệu trước mốc chia')
    calendar=infer_market_days({s:closed[s] for s in reference})
    train_days=calendar[calendar<=cut];test_days=calendar[calendar>cut]
    th=Thresholds();minimum=max(th.avg_window,th.trend_window+1)+3+max(horizons)
    if len(train_days)<minimum or len(test_days)<=max(horizons):
        raise ValueError(f'Cần ít nhất {minimum} phiên train và {max(horizons)+1} phiên test')
    cut=train_days[-1]
    protocol=dict(version=2,design='retrospective_chronological_holdout',
        prior_full_sample_inspection=True,train_start=str(train_days[0].date()),train_end=str(cut.date()),
        test_start=str(test_days[0].date()),initial_asof=str(asof.date()),
        requested_train_fraction=train_fraction,realized_train_fraction=len(train_days)/len(calendar),
        n_train_sessions=len(train_days),n_test_sessions_initial=len(test_days),
        universe=sorted(frames),calendar_reference_symbols=reference,
        horizons=list(horizons),fees_bps=list(fees),thresholds=asdict(th),
        tuning='none; thresholds, horizons, costs and primary family fixed before this holdout run',
        primary_family=int(pattern_catalog('pattern').bias.ne('neutral').sum())*len(horizons)*len(fees)*2,
        q3_smoothing='Laplace (successes+1)/(n+2); pooled training rate fallback',
        q3_baseline='single pooled Laplace training probability for both setup types',
        boundary_policy='training labels whose exit/confirmation crosses cut are purged; test may use past warmup prices',
        q3_score_family=6,
        execution_slippage_bps=[0,10,20],
        execution_policy='descriptive long only; no assumed fills at one-price or nonpositive/unknown-volume entry/exit',
        block_rule='Q2 max(requested block size, 5*h); Q3 requested block size',
        min_calendar_blocks=10,
        inference='Q2 studentized two-sample circular block bootstrap train+test; Q3 paired ratio block bootstrap; separate prespecified BY families')
    return protocol,calendar


def training_fingerprint(frames,issues,train_end):
    """Dấu vân tay phần train: thay đổi giá/quality cũ đòi hỏi nghiên cứu phiên bản mới."""
    cut=pd.Timestamp(train_end);digest=hashlib.sha256()
    for symbol in sorted(frames):
        f=frames[symbol].loc[frames[symbol].index<=cut].sort_index()
        digest.update(symbol.encode());digest.update(f.to_csv(date_format='%Y-%m-%dT%H:%M:%S',lineterminator='\n').encode())
    if issues is not None and not issues.empty:
        q=issues[pd.to_datetime(issues.trading_date)<=cut].copy()
        if not q.empty: digest.update(q.sort_values(list(q.columns)).to_csv(index=False,lineterminator='\n').encode())
    return digest.hexdigest()


def q3_oos_tables(train_outcomes,test_outcomes,train_end,test_calendar=None,block_size=20,resamples=1000):
    """Ước lượng xác suất bằng train, chấm Brier/log loss bằng nhãn test đã biết."""
    cut=pd.Timestamp(train_end)
    train=train_outcomes[(pd.to_datetime(train_outcomes.setup_date)<=cut)&
        (pd.to_datetime(train_outcomes.next_date)<=cut)&
        train_outcomes.status.isin(['completed','not_completed'])].copy()
    test=test_outcomes.copy()
    if not test.empty and (pd.to_datetime(test.setup_date)<=cut).any():
        raise ValueError('Setup test phải xuất hiện SAU mốc train')
    total=len(train);success=int(train.status.eq('completed').sum())
    pooled=(success+1)/(total+2) if total else np.nan
    model=[]
    for name,(_,label) in PAIRS.items():
        part=train[train.setup==name];n=len(part);k=int(part.status.eq('completed').sum())
        model.append(dict(setup=name,name_vi=label,n_train=n,n_train_completed=k,
            train_probability_raw=k/n if n else np.nan,
            forecast_probability=(k+1)/(n+2) if n else pooled,
            forecast_source='setup_train' if n else 'pooled_train_fallback' if total else 'unavailable',
            baseline_forecast_probability=pooled,fit_end=cut))
    model=pd.DataFrame(model)
    prediction=test.merge(model[['setup','forecast_probability','baseline_forecast_probability','forecast_source']],on='setup',how='left',validate='many_to_one')
    prediction['observed_completed']=prediction.status.map({'completed':1.,'not_completed':0.})
    prediction['scored']=prediction.observed_completed.notna()&prediction.forecast_probability.notna()
    for label,column in [('model','forecast_probability'),('baseline','baseline_forecast_probability')]:
        p=prediction[column].clip(1e-12,1-1e-12);y=prediction.observed_completed
        prediction['brier_'+label]=((p-y)**2).where(prediction.scored)
        prediction['logloss_'+label]=(-(y*np.log(p)+(1-y)*np.log(1-p))).where(prediction.scored)
    rows=[]
    groups=[(r.setup,r.name_vi,r.n_train,r.n_train_completed,r.forecast_probability) for r in model.itertuples(index=False)]
    groups.append(('all','Tất cả cảnh báo',total,success,np.nan))
    for name,label,n,k,forecast in groups:
        part=prediction if name=='all' else prediction[prediction.setup==name]
        evaluated=part[part.observed_completed.notna()];scored=part[part.scored]
        observed=int(evaluated.status.eq('completed').sum());low,high=wilson_interval(observed,len(evaluated))
        brier=scored.brier_model.mean();base=scored.brier_baseline.mean()
        row=dict(setup=name,name_vi=label,n_train=int(n),n_train_completed=int(k),
            train_probability_raw=k/n if n else np.nan,forecast_probability=forecast,baseline_forecast_probability=pooled,
            n_test_total=len(part),n_test_evaluated=len(evaluated),n_test_scored=len(scored),
            n_test_completed=observed,n_test_pending=int(part.status.eq('pending').sum()),
            n_test_excluded=int(part.status.isin(['missing_next_bar','invalid_next_bar']).sum()),
            test_probability=observed/len(evaluated) if len(evaluated) else np.nan,
            test_ci_low=low,test_ci_high=high,mean_forecast_on_scored=scored.forecast_probability.mean(),
            brier_model=brier,brier_baseline=base,brier_skill=1-brier/base if pd.notna(base) and base>0 else np.nan,
            logloss_model=scored.logloss_model.mean(),logloss_baseline=scored.logloss_baseline.mean())
        if test_calendar is not None:
            count=scored.groupby('setup_date').size().astype(float)
            for metric in ('brier','logloss'):
                delta=scored[metric+'_baseline']-scored[metric+'_model']
                sums=delta.groupby(scored.setup_date).sum()
                result=ratio_block_test(sums,count,test_calendar,block_size,resamples)
                for key,value in result.items():row[f'{metric}_gain_{key}']=value
            rates=evaluated.groupby('setup_date').observed_completed.agg(['sum','count'])
            rate=ratio_block_test(rates['sum'],rates['count'],test_calendar,block_size,resamples)
            for key in ('low','high','n_dates','effective_resamples'):row['test_block_'+key]=rate[key]
        rows.append(row)
    summary=pd.DataFrame(rows)
    for metric in ('brier','logloss'):
        if metric+'_gain_p' not in summary:summary[metric+'_gain_p']=np.nan
    adjusted=fdr_by(np.column_stack([summary.brier_gain_p,summary.logloss_gain_p]).reshape(-1),n_tests=6).reshape(-1,2)
    summary['brier_gain_q']=adjusted[:,0];summary['logloss_gain_q']=adjusted[:,1]
    return model,summary,prediction


def oos_tables(frames,asof,issues,protocol,resamples=39999,block_size=20):
    """Chạy một holdout đã chốt: fit trước, đánh giá sau; không chọn nhãn thắng."""
    cut=pd.Timestamp(protocol['train_end']);start=pd.Timestamp(protocol['test_start'])
    horizons=tuple(protocol['horizons']);fees=tuple(protocol['fees_bps'])
    if protocol['thresholds']!=asdict(Thresholds()):raise ValueError('Ngưỡng hiện tại khác protocol đã khóa')
    closed={s:f.loc[f.index<=pd.Timestamp(asof)] for s,f in frames.items()}
    calendar=infer_market_days({s:closed[s] for s in protocol['calendar_reference_symbols']})
    train_days=calendar[calendar<=cut];test_days=calendar[calendar>=start]
    train_radar=build_radar(closed,cut,issues,market_days=train_days)
    test_radar=build_radar(closed,asof,issues,market_days=calendar)
    test_events=test_radar.events[test_radar.events.date>=start].copy()
    models=pd.concat([fit_event_baselines(closed,cut,issues,horizons,fee,market_days=train_days) for fee in fees],ignore_index=True)
    train_summary,train_detail,family=q2_tables(closed,train_radar.events,cut,issues,horizons,fees,
        resamples,block_size,market_days=train_days,inference=False)
    test_summary,test_detail,test_family=q2_tables(closed,test_events,asof,issues,horizons,fees,
        resamples,block_size,baselines=models,market_days=calendar,evaluation_start=start)
    if family!=protocol['primary_family'] or test_family!=family:raise ValueError('Họ kiểm định khác protocol')
    train_detail['purged_boundary']=train_detail.status.eq('pending')
    compare_keys=['Mẫu hình','Số phiên','fee_bps','bias']
    compare=train_summary.merge(test_summary,on=compare_keys,suffixes=('_train','_test'),validate='one_to_one')
    train_setups=build_setup_outcomes(closed,cut,issues,market_days=train_days)
    test_setups=build_setup_outcomes(closed,asof,issues,market_days=calendar)
    test_setups=test_setups[pd.to_datetime(test_setups.setup_date)>=start].copy()
    model,q3,prediction=q3_oos_tables(train_setups,test_setups,cut,test_days,block_size,resamples)
    train_setups['purged_boundary']=train_setups.status.eq('pending')
    ty,ts=q1_tables(train_radar.events);vy,vs=q1_tables(test_events)
    tables={'q1_train_pattern_year.csv':ty,'q1_train_pattern_symbol.csv':ts,
        'q1_oos_pattern_year.csv':vy,'q1_oos_pattern_symbol.csv':vs,
        'signals_train.csv':train_radar.events,'signals_oos.csv':test_events,
        'q2_train_baselines.csv':models,'q2_train_summary.csv':train_summary,
        'q2_train_outcomes.csv':train_detail,'q2_oos_summary.csv':test_summary,
        'q2_oos_outcomes.csv':test_detail,'q2_train_oos_comparison.csv':compare,
        'execution_stress.csv':execution_stress(test_detail),
        'q3_train_model.csv':model,'q3_train_outcomes.csv':train_setups,
        'q3_oos_outcomes.csv':test_setups,'q3_oos_summary.csv':q3,'q3_oos_predictions.csv':prediction,
        'split_assignments.csv':pd.DataFrame({'date':calendar,'partition':np.where(calendar<=cut,'train','test')})}
    return tables
