"""Lợi suất từ mở cửa t+1; loại cửa sổ thiếu/lỗi và không dùng tương lai sau asof."""
import numpy as np
import pandas as pd
from analytics.radar import infer_market_days, _valid_rows
from analytics.multiple_testing import fdr_by


def event_outcomes(frames, events, asof, issues=None, horizons=(5,10,20), fee_bps=20):
    if not 0 <= fee_bps < 10000:
        raise ValueError('Chi phí phải trong khoảng 0 đến dưới 10000 bps')
    frames = {s:f.loc[f.index <= pd.Timestamp(asof)].sort_index() for s,f in frames.items()}
    calendar = infer_market_days(frames)
    baselines={}
    for symbol,f in frames.items():
        aligned=f.reindex(calendar);valid=_valid_rows(aligned)
        if issues is not None and not issues.empty:
            bad=pd.to_datetime(issues.loc[(issues.symbol==symbol)&(issues.severity=='error'),'trading_date'])
            valid &= ~calendar.isin(bad)
        for h in horizons:
            eligible=valid.rolling(h,min_periods=h).sum().shift(-h).eq(h)
            fee=fee_bps/20000
            net=aligned.close.shift(-h)*(1-fee)/(aligned.open.shift(-1)*(1+fee))-1
            baselines[(symbol,h)]=net[eligible].mean()
    rows=[]
    for e in events.loc[(events.kind == 'pattern') & (events.date <= pd.Timestamp(asof))].itertuples(index=False):
        f=frames[e.symbol]
        for h in horizons:
            r=dict(symbol=e.symbol,name=e.name,name_vi=e.name_vi,bias=e.bias,date=e.date,horizon=h,status='pending',gross=np.nan,net=np.nan,mae=np.nan,entry_date=pd.NaT,exit_date=pd.NaT)
            pos=calendar.searchsorted(pd.Timestamp(e.date),side='right')
            window=calendar[pos:pos+h]
            if len(window)==h:
                if not window.isin(f.index).all(): r['status']='missing'
                else:
                    bars=f.loc[window]
                    invalid=not _valid_rows(bars).all()
                    if issues is not None and not issues.empty:
                        bad=pd.to_datetime(issues.loc[(issues.symbol==e.symbol)&(issues.severity=='error'),'trading_date'])
                        invalid=invalid or window.isin(bad).any()
                    if invalid: r['status']='invalid'
                    else:
                        entry=float(bars.open.iloc[0]);exit=float(bars.close.iloc[-1]);fee=fee_bps/20000
                        r.update(status='evaluated',entry_date=window[0],exit_date=window[-1],gross=exit/entry-1,
                                 net=exit*(1-fee)/(entry*(1+fee))-1,mae=min(0.,bars.low.min()/entry-1))
            r['excess']=r['net']-baselines.get((e.symbol,h),np.nan)
            rows.append(r)
    return pd.DataFrame(rows,columns=['symbol','name','name_vi','bias','date','horizon','status','gross','net','mae','entry_date','exit_date','excess'])


def summarize_events(outcomes):
    rows=[]
    if outcomes.empty: return pd.DataFrame()
    for (name,h),g in outcomes.groupby(['name_vi','horizon']):
        good=g[g.status=='evaluated']
        daily=good.groupby('date').excess.mean().dropna().to_numpy()
        daily = np.where(np.abs(daily) < 1e-12, 0.0, daily)
        lower=upper=p=np.nan
        if len(good)>=30 and len(daily)>=20:
            rng=np.random.default_rng(2026);n=len(daily);length=min(20,n)
            starts=rng.integers(0,n,size=(1000,int(np.ceil(n/length))))
            indices=(starts[:,:,None]+np.arange(length))%n
            means=daily[indices.reshape(1000,-1)[:,:n]].mean(axis=1)
            lower,upper=np.quantile(means,[.025,.975])
            p=(1+np.sum(np.abs(means-daily.mean())>=abs(daily.mean())))/1001
        rows.append({'Mẫu hình':name,'Số phiên':h,'Tổng nhãn':len(g),'Đủ dữ liệu':len(good),
                     'Chưa đủ tương lai':int(g.status.eq('pending').sum()),'Loại thiếu/lỗi':int(g.status.isin(['missing','invalid']).sum()),
                     'Lợi suất giá TB (%)':good.gross.mean()*100,'Long sau phí TB (%)':good.net.mean()*100,
                     'Tỷ lệ giá tăng (%)':good.gross.gt(0).mean()*100 if len(good) else np.nan,
                     'Bất lợi TB (%)':good.mae.mean()*100,'Chênh nền TB theo ngày (%)':daily.mean()*100 if len(daily) else np.nan,
                     'CI95 dưới (%)':lower*100,'CI95 trên (%)':upper*100,'p bootstrap':p})
    result=pd.DataFrame(rows);result['q BY']=fdr_by(result['p bootstrap'])
    return result
