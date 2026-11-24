"""Q3 bổ sung: nến 2 có thêm thông tin so với cùng điều kiện nến 1 hay không?"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
from _support import parent_report,snapshot,output_folder,csv,finish,utf8
from finance.candles import Thresholds,describe_candles

NAMES={'morning_star_setup':'Sao mai','evening_star_setup':'Sao hôm'}


def candidates(frames,issues,calendar,th):
    """Hai nhóm dùng cùng nến 1; outcome chỉ kiểm tra màu/midpoint ở nến thứ ba.

    Kiểm tra đủ cửa sổ liên tiếp như radar, không nối qua ngày thiếu/lỗi.
    Không dùng future để xác định nhóm ở nến 2; chỉ outcome cần nến 3.
    """
    calendar=pd.DatetimeIndex(calendar);rows=[]
    for symbol,original in frames.items():
        f=original.reindex(calendar).copy();px=f[['open','high','low','close']]
        valid=np.isfinite(px).all(axis=1)&px.gt(0).all(axis=1)
        valid &= f.high.ge(f[['open','close']].max(axis=1))&f.low.le(f[['open','close']].min(axis=1))
        if 'volume' in f:valid &= f.volume.isna()|(np.isfinite(f.volume)&f.volume.ge(0))
        if issues is not None and not issues.empty:
            blocked=pd.to_datetime(issues.loc[issues.symbol.eq(symbol)&issues.severity.eq('error'),'trading_date'])
            valid &= ~f.index.isin(blocked)
        clean=f.loc[valid]
        if clean.empty:continue
        d=describe_candles(clean,th).reindex(calendar)
        eligible=valid.rolling(max(th.avg_window,th.trend_window+1)+2).sum().eq(max(th.avg_window,th.trend_window+1)+2)
        for setup in NAMES:
            bullish=setup.startswith('morning')
            trend=d.trend_t.shift(2).le(-th.trend_t) if bullish else d.trend_t.shift(2).ge(th.trend_t)
            first_color=d.black.shift(1).eq(True) if bullish else d.white.shift(1).eq(True)
            stage1=eligible&trend&first_color&d.long_body.shift(1).eq(True)
            gap=d.body_top.lt(d.body_bot.shift(1)) if bullish else d.body_bot.gt(d.body_top.shift(1))
            alarm=d.short_body.eq(True)&gap
            for pos in np.flatnonzero(stage1.to_numpy()):
                day=calendar[pos];next_day=calendar[pos+1] if pos+1<len(calendar) else pd.NaT
                if pd.isna(next_day):status='pending';y=np.nan
                elif next_day not in original.index:status='missing_next_bar';y=np.nan
                elif not valid.iloc[pos+1]:status='invalid_next_bar';y=np.nan
                else:
                    first=f.iloc[pos-1];third=f.iloc[pos+1];mid=(first.open+first.close)/2
                    y=int(third.close>third.open and third.close>mid) if bullish else int(third.close<third.open and third.close<mid)
                    status='completed' if y else 'not_completed'
                rows.append(dict(symbol=symbol,setup=setup,setup_date=day,next_date=next_day,
                    arm='alarm' if bool(alarm.iloc[pos]) else 'first_candle_only',status=status,outcome=y))
    return pd.DataFrame(rows,columns=['symbol','setup','setup_date','next_date','arm','status','outcome'])


def block_draws(daily,calendar,resamples=39999,length=20,seed=2026):
    """Một lịch lấy mẫu chung cho mọi mã/nhóm, gồm cả ngày không có nhãn."""
    if len(calendar)==0 or length<1 or resamples<1:raise ValueError('Lịch/khối/số lượt lấy mẫu phải dương')
    values=daily.reindex(calendar,fill_value=0).to_numpy(dtype=float)
    n=len(values);length=min(length,n)
    def table(k):
        x=np.vstack([values,values[:k-1]]) if k>1 else values
        sums=np.vstack([np.zeros((1,values.shape[1])),np.cumsum(x,axis=0)])
        return sums[k:]-sums[:-k]
    full=table(length);remainder=n%length;last=table(remainder) if remainder else None
    rng=np.random.default_rng(seed)
    for offset in range(0,resamples,128):
        size=min(128,resamples-offset);starts=rng.integers(0,n,size=(size,int(np.ceil(n/length))))
        totals=full[starts[:,:n//length]].sum(axis=1)
        if remainder:totals+=last[starts[:,-1]]
        yield totals


def bootstrap_metric(point,draws,resamples,eligible):
    draws=np.asarray(draws);draws=draws[np.isfinite(draws)]
    result=dict(mean=float(point),low=np.nan,high=np.nan,low_family=np.nan,high_family=np.nan,effective_resamples=len(draws))
    if eligible and np.isfinite(point) and len(draws)>=resamples*.8:
        low,high=np.quantile(draws,[.025,.975])
        family_low,family_high=np.quantile(draws,[.05/12,1-.05/12])
        result.update(low=float(low),high=float(high),low_family=float(family_low),high_family=float(family_high))
    return result


def pooled_comparison(part,calendar,resamples=39999,block_size=20):
    good=part[part.outcome.notna()];daily=pd.DataFrame(0.,index=calendar,columns=['ty','tn','cy','cn'])
    for (day,arm),g in good.groupby(['setup_date','arm']):
        prefix='t' if arm=='alarm' else 'c';daily.loc[day,[prefix+'y',prefix+'n']]=[g.outcome.sum(),len(g)]
    def rates(x):
        x=np.atleast_2d(x);a=np.divide(x[:,0],x[:,1],out=np.full(len(x),np.nan),where=x[:,1]>0)
        b=np.divide(x[:,2],x[:,3],out=np.full(len(x),np.nan),where=x[:,3]>0)
        return a,b,a-b
    point=rates(daily.sum().to_numpy());samples=[[],[],[]]
    for draw in block_draws(daily,calendar,resamples,block_size):
        for bucket,value in zip(samples,rates(draw)):bucket.extend(value)
    n_t=int(good.arm.eq('alarm').sum());n_c=int(good.arm.eq('first_candle_only').sum())
    dates=good.loc[good.arm.eq('alarm'),'setup_date'].nunique()
    eligible=n_t>=30 and n_c>=30 and dates>=20 and len(calendar)//block_size>=10
    result=dict(n_alarm=n_t,n_control=n_c,n_alarm_dates=dates,eligible=eligible,weighting='pooled label rates; arms and dates resampled jointly')
    for label,estimate,draws in zip(['alarm_rate','control_rate','gap'],point,samples):
        for key,value in bootstrap_metric(estimate[0],draws,resamples,eligible).items():result[label+'_'+key]=value
    return result


def comparison(part,calendar,resamples=39999,block_size=20):
    good=part[part.outcome.notna()].copy()
    counts=good.groupby(['symbol','arm']).size().unstack(fill_value=0).reindex(columns=['alarm','first_candle_only'],fill_value=0)
    matched=counts.index[(counts.alarm>0)&(counts.first_candle_only>0)]
    unmatched=int(good.arm.eq('alarm').sum()-good[good.symbol.isin(matched)].arm.eq('alarm').sum())
    good=good[good.symbol.isin(matched)];symbols=sorted(matched)
    # 4 tổng cho từng mã: số hoàn thành/số nhãn ở từng nhóm.
    columns=pd.MultiIndex.from_product([symbols,['ty','tn','cy','cn']])
    daily=pd.DataFrame(0.,index=calendar,columns=columns)
    for (symbol,arm,day),g in good.groupby(['symbol','arm','setup_date']):
        prefix='t' if arm=='alarm' else 'c'
        daily.loc[day,(symbol,prefix+'y')]=g.outcome.sum()
        daily.loc[day,(symbol,prefix+'n')]=len(g)
    def estimates(totals):
        x=np.asarray(totals).reshape(-1,len(symbols),4)
        weights=x[:,:,1];matched=(weights==0)|(x[:,:,3]>0)
        t=weights.sum(axis=1)
        a=np.divide(x[:,:,0].sum(axis=1),t,out=np.full(len(x),np.nan),where=t>0)
        c=np.divide(x[:,:,2],x[:,:,3],out=np.zeros_like(weights),where=x[:,:,3]>0)
        b=np.divide((weights*c).sum(axis=1),t,out=np.full(len(x),np.nan),where=(t>0)&matched.all(axis=1))
        return a,b,a-b
    if not symbols:return dict(n_alarm=0,n_control=0,n_alarm_unmatched=unmatched,gap_mean=np.nan)
    point=estimates(daily.sum().to_numpy());samples=[[],[],[]]
    for draw in block_draws(daily,calendar,resamples,block_size):
        for bucket,value in zip(samples,estimates(draw)):bucket.extend(value)
    n_t=int(good.arm.eq('alarm').sum());n_c=int(good.arm.eq('first_candle_only').sum())
    dates=good.loc[good.arm.eq('alarm'),'setup_date'].nunique()
    eligible=n_t>=30 and n_c>=30 and dates>=20 and len(calendar)//block_size>=10
    row=dict(n_alarm=n_t,n_control=n_c,n_alarm_unmatched=unmatched,n_alarm_dates=dates,
        control_pooled=good.loc[good.arm.eq('first_candle_only'),'outcome'].mean(),
        weighting='control standardized to test alarm symbol frequencies; resampled jointly',eligible=eligible)
    for label,estimate,draws in zip(['alarm_rate','control_rate','gap'],point,samples):
        for key,value in bootstrap_metric(estimate[0],draws,resamples,eligible).items():row[label+'_'+key]=value
    return row


def score_forecasts(train,test,calendar,resamples=39999,block_size=20):
    train=train[train.outcome.notna()];model={};rows=[];predictions=[]
    for name in NAMES:
        g=train[train.setup==name];prob={}
        for arm in ['alarm','first_candle_only']:
            s=g[g.arm==arm];prob[arm]=(s.outcome.sum()+1)/(len(s)+2) if len(s) else np.nan
        model[name]=prob
        part=test[test.setup.eq(name)&test.arm.eq('alarm')&test.outcome.notna()].copy()
        part['forecast_alarm']=prob['alarm'];part['forecast_control']=prob['first_candle_only']
        valid=part.forecast_alarm.notna()&part.forecast_control.notna();scored=part.loc[valid].copy()
        row=dict(setup=name,n_test_scored=len(scored),forecast_alarm=prob['alarm'],forecast_control=prob['first_candle_only'],
            n_train_alarm=int(g.arm.eq('alarm').sum()),n_train_control=int(g.arm.eq('first_candle_only').sum()))
        for metric in ['brier','logloss']:
            for arm in ['alarm','control']:
                p=scored['forecast_'+arm].clip(1e-12,1-1e-12);y=scored.outcome
                scored[metric+'_'+arm]=(p-y)**2 if metric=='brier' else -(y*np.log(p)+(1-y)*np.log(1-p))
            delta=scored[metric+'_control']-scored[metric+'_alarm']
            sums=delta.groupby(scored.setup_date).sum();count=scored.groupby('setup_date').size()
            daily=pd.DataFrame({'delta':sums,'count':count}).reindex(calendar,fill_value=0.)
            draws=[]
            for sample in block_draws(daily,calendar,resamples,block_size):
                draws.extend(np.divide(sample[:,0],sample[:,1],out=np.full(len(sample),np.nan),where=sample[:,1]>0))
            eligible=len(scored)>=30 and scored.setup_date.nunique()>=20 and len(calendar)//block_size>=10
            result=bootstrap_metric(delta.mean(),draws,resamples,eligible)
            row[metric+'_alarm']=scored[metric+'_alarm'].mean();row[metric+'_control']=scored[metric+'_control'].mean()
            for key,value in result.items():row[metric+'_gain_'+key]=value
        predictions.append(scored);rows.append(row)
    return pd.DataFrame(rows),pd.concat(predictions,ignore_index=True)


def split_rows(rows,cut):
    cut=pd.Timestamp(cut)
    return (rows[(rows.setup_date<=cut)&(rows.next_date<=cut)].copy(),
            rows[rows.setup_date>cut].copy())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',default='report/oos_verified');p.add_argument('--db',default='storage/radar.db')
    p.add_argument('--out',default='report/supplement_20261124/q3_incremental');p.add_argument('--resamples',type=int,default=39999)
    a=p.parse_args()
    if a.resamples<99:p.error('--resamples >=99')
    source,m=parent_report(a.study);frames,issues=snapshot(a.db,m);out=output_folder(a.out,source)
    assignments=pd.read_csv(source/'split_assignments.csv',parse_dates=['date']);calendar=pd.DatetimeIndex(assignments.date)
    cut=pd.Timestamp(m['protocol']['train_end']);test_calendar=calendar[calendar>cut]
    all_rows=candidates(frames,issues,calendar,Thresholds(**m['protocol']['thresholds']))
    train,test=split_rows(all_rows,cut)
    # Nhóm alarm phải tái tạo đúng kết quả chính đã lưu, trước khi thêm đối chứng.
    for subset,name in [(train,'q3_train_outcomes.csv'),(test,'q3_oos_outcomes.csv')]:
        expected=pd.read_csv(source/name,parse_dates=['setup_date','next_date'])
        expected=expected[(expected.setup_date>cut) if name.startswith('q3_oos') else (expected.next_date<=cut)]
        actual=subset[subset.arm=='alarm']
        cols=['symbol','setup','setup_date','next_date','status']
        expected=expected[cols].sort_values(cols[:3]).reset_index(drop=True)
        actual=actual[cols].sort_values(cols[:3]).reset_index(drop=True)
        pd.testing.assert_frame_equal(actual,expected,check_dtype=False)
    rates=pd.DataFrame([dict(setup=name,**pooled_comparison(test[test.setup==name],test_calendar,a.resamples)) for name in NAMES])
    matched=pd.DataFrame([dict(setup=name,**comparison(test[test.setup==name],test_calendar,a.resamples)) for name in NAMES])
    scores,predictions=score_forecasts(train,test,test_calendar,a.resamples)
    csv(out,'candidate_outcomes.csv',all_rows);csv(out,'q3_rate_comparison.csv',rates);csv(out,'q3_rate_symbol_standardized.csv',matched)
    csv(out,'q3_train_forecast_scores.csv',scores);csv(out,'alarm_predictions.csv',predictions)
    finish(out,'Q3_incremental_second_candle',source,dict(train_end=str(cut.date()),resamples=a.resamples,block_size=20,
        interval_family_size=6,seed=2026,alarm_reproduces_primary=True,
        intervals='percentile circular block 95%; Bonferroni nominal family bounds at 1-0.05/6; approximate coverage',
        p_values='not reported; no calibrated null p-test claimed from percentile CIs',
        outcome='third candle direction and close beyond first-body midpoint in both groups',
        cautions=['association, not causal effect of candle 2','scores conditional on fixed Laplace training forecasters',
        'primary rate gap uses pooled contemporaneous test controls; symbol-standardization is a sensitivity only',
        'circular day blocks include no-label days; same blocks for both arms and all symbols']),__file__)
    print(rates.to_string(index=False));print(scores.to_string(index=False))


if __name__=='__main__':utf8();main()
