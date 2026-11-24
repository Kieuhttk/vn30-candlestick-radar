"""Lợi suất t+1..t+h; hỗ trợ mức nền cố định ước lượng trước tập đánh giá."""
from dataclasses import asdict
import hashlib
import json
import numpy as np
import pandas as pd
from analytics.radar import infer_market_days, _valid_rows
from analytics.multiple_testing import fdr_by
from finance.candles import Thresholds
from finance.patterns import pattern_catalog

BASELINE_VALUES = ['baseline_net','conditional_baseline_net','baseline_hit','conditional_baseline_hit',
                   'n_baseline','n_conditional_baseline']
OUTCOME_COLUMNS = ['symbol','name','name_vi','bias','date','horizon','status','gross','net','mae',
                   'entry_date','exit_date','excess','conditional_excess','oriented_excess',
                   'oriented_conditional_excess','direction_hit',*BASELINE_VALUES,
                   'baseline_fit_end','baseline_available','conditional_baseline_available']
OUTCOME_COLUMNS += ['entry_volume','exit_volume','entry_one_price','exit_one_price']
REVERSALS = set(pattern_catalog('pattern').name) - {
    'doji','dragonfly_doji','gravestone_doji','long_legged_doji','spinning_top',
    'marubozu_white','marubozu_black'}


def _validate(horizons, fee_bps):
    if not 0 <= fee_bps < 10000:raise ValueError('Chi phí phải trong khoảng 0 đến dưới 10000 bps')
    if not horizons or any(int(h)!=h or h<1 for h in horizons):raise ValueError('Kỳ hạn phải là số nguyên dương')
    if len(set(horizons))!=len(horizons):raise ValueError('Kỳ hạn không được trùng')


def _threshold_hash(th):
    return hashlib.sha256(json.dumps(asdict(th),sort_keys=True).encode()).hexdigest()


def _calendar(frames,asof,market_days=None):
    days=infer_market_days(frames) if market_days is None else pd.DatetimeIndex(market_days)
    days=days.drop_duplicates().sort_values()
    return days[days<=pd.Timestamp(asof)]


def _aligned(frame,calendar,symbol,issues):
    f=frame.reindex(calendar)
    present=pd.Series(calendar.isin(frame.index),index=calendar)
    valid=_valid_rows(f)
    if issues is not None and not issues.empty:
        bad=pd.to_datetime(issues.loc[(issues.symbol==symbol)&(issues.severity=='error'),'trading_date'])
        valid &= ~calendar.isin(bad)
    return f,present,valid


def _window(f,present,valid,h,fee_bps):
    fee=fee_bps/20000
    physical=present.rolling(h).sum().shift(-h).eq(h)
    eligible=valid.rolling(h).sum().shift(-h).eq(h)
    gross=f.close.shift(-h)/f.open.shift(-1)-1
    net=f.close.shift(-h)*(1-fee)/(f.open.shift(-1)*(1+fee))-1
    mae=(f.low.rolling(h).min().shift(-h)/f.open.shift(-1)-1).clip(upper=0)
    return physical,eligible,gross,net,mae


def _baseline_masks(valid,trend,eligible,info,th):
    width=max(th.avg_window,th.trend_window+1)+int(info.candles)
    base=eligible&valid.rolling(width).sum().eq(width)
    t=trend.shift(int(info.candles))
    condition=t.le(-th.trend_t) if info.bias=='bullish' else t.ge(th.trend_t) if info.bias=='bearish' else pd.Series(True,index=valid.index)
    return base,base&condition if info.name in REVERSALS else base


def training_control_samples(frames,fit_end,name,horizon,fee_bps=20,issues=None,th=None,market_days=None):
    """Các cửa sổ TRAIN dùng để tính lại nền trong bootstrap; không chứa test."""
    th=th or Thresholds();_validate((horizon,),fee_bps)
    frames={s:f.loc[f.index<=pd.Timestamp(fit_end)].sort_index() for s,f in frames.items()}
    days=_calendar(frames,fit_end,market_days)
    catalog=pattern_catalog('pattern');matched=catalog[catalog.name==name]
    if matched.empty:raise ValueError('Mẫu hình không tồn tại: '+name)
    info=next(matched.itertuples(index=False))
    normal={};conditional={}
    for symbol,frame in frames.items():
        f,present,valid=_aligned(frame,days,symbol,issues)
        ret=np.log(f.close.where(valid)/f.close.where(valid).shift(1))
        trend=ret.rolling(th.trend_window).mean()/ret.rolling(th.trend_window).std()*np.sqrt(th.trend_window)
        _,eligible,_,net,_=_window(f,present,valid,horizon,fee_bps)
        base,condition=_baseline_masks(valid,trend,eligible,info,th)
        normal[symbol]=net.where(base);conditional[symbol]=net.where(condition)
    return pd.DataFrame(normal,index=days),pd.DataFrame(conditional,index=days)


def fit_event_baselines(frames,fit_end,issues=None,horizons=(1,3,5,10,20),fee_bps=20,
                        th=None,market_days=None,keys=None):
    """Chỉ dùng OHLC đến fit_end; cửa sổ lợi suất kết thúc sau mốc bị loại.

    keys chỉ giới hạn các hàng cần tính, không dùng nhãn/kết quả sự kiện để chọn mức nền.
    Mã chưa có dữ liệu train vẫn có hàng mô hình với n=0 và dự báo NaN.
    """
    th=th or Thresholds();_validate(horizons,fee_bps);fit_end=pd.Timestamp(fit_end).normalize()
    frames={s:f.loc[f.index<=fit_end].sort_index() for s,f in frames.items()}
    calendar=_calendar(frames,fit_end,market_days);catalog=pattern_catalog('pattern')
    rows=[];wanted=None if keys is None else set(keys);threshold_hash=_threshold_hash(th)
    for symbol,frame in frames.items():
        if wanted is not None and not any(key[0]==symbol for key in wanted):continue
        f,present,valid=_aligned(frame,calendar,symbol,issues)
        logret=np.log(f.close.where(valid)/f.close.where(valid).shift(1))
        trend=logret.rolling(th.trend_window).mean()/logret.rolling(th.trend_window).std()*np.sqrt(th.trend_window)
        for h in horizons:
            _,eligible,gross,net,_=_window(f,present,valid,h,fee_bps)
            for info in catalog.itertuples(index=False):
                if wanted is not None and (symbol,info.name,int(h)) not in wanted:continue
                base,conditional=_baseline_masks(valid,trend,eligible,info,th)
                direction=1 if info.bias=='bullish' else -1 if info.bias=='bearish' else np.nan
                hit=gross.gt(0) if direction==1 else gross.lt(0)
                rows.append(dict(symbol=symbol,name=info.name,horizon=int(h),fee_bps=fee_bps,
                    fit_start=calendar.min(),fit_end=fit_end,thresholds_hash=threshold_hash,
                    baseline_net=net[base].mean(),conditional_baseline_net=net[conditional].mean(),
                    baseline_hit=hit[base].mean() if base.any() and np.isfinite(direction) else np.nan,
                    conditional_baseline_hit=hit[conditional].mean() if conditional.any() and np.isfinite(direction) else np.nan,
                    n_baseline=int(base.sum()),n_conditional_baseline=int(conditional.sum())))
    return pd.DataFrame(rows,columns=['symbol','name','horizon','fee_bps','fit_start','fit_end','thresholds_hash',*BASELINE_VALUES])


def event_outcomes(frames, events, asof, issues=None, horizons=(1,3,5,10,20), fee_bps=20,
                   th=None, baselines=None, market_days=None):
    th=th or Thresholds();_validate(horizons,fee_bps);asof=pd.Timestamp(asof).normalize()
    frames={s:f.loc[f.index<=asof].sort_index() for s,f in frames.items()}
    calendar=_calendar(frames,asof,market_days);cat=pattern_catalog('pattern').set_index('name')
    chosen=events[(events.kind=='pattern')&(events.date<=asof)]
    if chosen.empty:return pd.DataFrame(columns=OUTCOME_COLUMNS)
    if not set(chosen.symbol).issubset(frames):raise ValueError('Sự kiện chứa mã không có trong frames')
    if baselines is None:
        keys={(e.symbol,e.name,int(h)) for e in chosen.itertuples(index=False) for h in horizons}
        baselines=fit_event_baselines(frames,asof,issues,horizons,fee_bps,th,calendar,keys)
    else:
        required={'symbol','name','horizon','fee_bps','fit_end','thresholds_hash',*BASELINE_VALUES}
        if not required.issubset(baselines.columns):raise ValueError('Mô hình mức nền thiếu cột')
        baselines=baselines[baselines.fee_bps.eq(fee_bps)].copy()
        if baselines.empty:raise ValueError('Mô hình mức nền không có mức phí yêu cầu')
        if not baselines.thresholds_hash.eq(_threshold_hash(th)).all():raise ValueError('Ngưỡng nhận diện khác mô hình đã fit')
        fit_dates=pd.to_datetime(baselines.fit_end)
        if fit_dates.isna().any() or (fit_dates>=pd.to_datetime(chosen.date).min()).any():
            raise ValueError('Mức nền ngoài mẫu phải được fit TRƯỚC mọi ngày tín hiệu đánh giá')
    if baselines.duplicated(['symbol','name','horizon']).any():raise ValueError('Trùng khóa mô hình mức nền')
    models=baselines.set_index(['symbol','name','horizon']);rows=[]
    for symbol,group in chosen.groupby('symbol'):
        f,present,valid=_aligned(frames[symbol],calendar,symbol,issues)
        for h in horizons:
            enough=pd.Series(np.arange(len(calendar))+h<len(calendar),index=calendar)
            physical,eligible,gross,net,mae=_window(f,present,valid,h,fee_bps)
            for name,signals in group.groupby('name'):
                if name not in cat.index:continue
                key=(symbol,name,int(h))
                if key not in models.index:raise ValueError('Mô hình mức nền thiếu khóa: '+str(key))
                model=models.loc[key];info=cat.loc[name]
                direction=1 if info.bias=='bullish' else -1 if info.bias=='bearish' else np.nan
                for e in signals.itertuples(index=False):
                    day=pd.Timestamp(e.date)
                    r=dict(symbol=symbol,name=name,name_vi=e.name_vi,bias=e.bias,date=day,horizon=int(h),
                        status='pending',gross=np.nan,net=np.nan,mae=np.nan,entry_date=pd.NaT,exit_date=pd.NaT,
                        excess=np.nan,conditional_excess=np.nan,oriented_excess=np.nan,oriented_conditional_excess=np.nan,
                        direction_hit=np.nan,baseline_fit_end=pd.Timestamp(model.fit_end),
                        entry_volume=np.nan,exit_volume=np.nan,entry_one_price=np.nan,exit_one_price=np.nan,
                        baseline_available=bool(model.n_baseline>0 and pd.notna(model.baseline_net)),
                        conditional_baseline_available=bool(model.n_conditional_baseline>0 and pd.notna(model.conditional_baseline_net)),
                        **{column:model[column] for column in BASELINE_VALUES})
                    if day not in calendar:r['status']='invalid'
                    elif enough.loc[day]:
                        if not physical.loc[day]:r['status']='missing'
                        elif not eligible.loc[day]:r['status']='invalid'
                        else:
                            pos=calendar.get_loc(day)
                            r.update(status='evaluated',gross=float(gross.loc[day]),net=float(net.loc[day]),mae=float(mae.loc[day]),
                                     entry_date=calendar[pos+1],exit_date=calendar[pos+h])
                            entry=f.iloc[pos+1];exit=f.iloc[pos+h]
                            r.update(entry_volume=float(entry.get('volume',np.nan)),exit_volume=float(exit.get('volume',np.nan)),
                                     entry_one_price=bool(entry.high==entry.low),exit_one_price=bool(exit.high==exit.low))
                            r['excess']=r['net']-r['baseline_net'];r['conditional_excess']=r['net']-r['conditional_baseline_net']
                            r['oriented_excess']=direction*r['excess'];r['oriented_conditional_excess']=direction*r['conditional_excess']
                            r['direction_hit']=float(r['gross']*direction>0) if np.isfinite(direction) else np.nan
                    rows.append(r)
    return pd.DataFrame(rows,columns=OUTCOME_COLUMNS)


def summarize_events(outcomes, calendar=None, block_size=20, resamples=1000, inference=True):
    from analytics.inference import block_test
    rows=[]
    if outcomes.empty: return pd.DataFrame()
    for (name,h),g in outcomes.groupby(['name_vi','horizon']):
        good=g[g.status=='evaluated']
        daily=good.groupby('date').excess.mean().dropna().to_numpy()
        # Pandas Copy-on-Write có thể trả mảng chỉ đọc; tạo mảng mới.
        daily = np.where(np.abs(daily) < 1e-12, 0.0, daily)
        tested=block_test(good.groupby('date').excess.mean(),calendar,block_size,resamples) if inference and good.excess.notna().sum()>=30 else dict(low=np.nan,high=np.nan,p=np.nan)
        lower,upper,p=tested['low'],tested['high'],tested['p']
        rows.append({'Mẫu hình':name,'Số phiên':h,'Tổng nhãn':len(g),'Đủ dữ liệu':len(good),
                     'Chưa đủ tương lai':int(g.status.eq('pending').sum()),'Loại thiếu/lỗi':int(g.status.isin(['missing','invalid']).sum()),
                     'Lợi suất giá TB (%)':good.gross.mean()*100,'Long sau phí TB (%)':good.net.mean()*100,
                     'Tỷ lệ giá tăng (%)':good.gross.gt(0).mean()*100 if len(good) else np.nan,
                     'Bất lợi TB (%)':good.mae.mean()*100,'Chênh nền TB theo ngày (%)':daily.mean()*100 if len(daily) else np.nan,
                     'CI95 dưới (%)':lower*100,'CI95 trên (%)':upper*100,'p bootstrap':p})
    result=pd.DataFrame(rows)
    extra=[]
    for (name,h),g in outcomes.groupby(['name_vi','horizon']):
        good=g[g.status=='evaluated'];bias=g.bias.iloc[0] if 'bias' in g else 'neutral'
        row={'Mẫu hình':name,'Số phiên':h,'bias':bias}
        row['n_with_baseline']=int(good.excess.notna().sum())
        row['n_with_trend_baseline']=int(good.conditional_excess.notna().sum()) if 'conditional_excess' in good else 0
        for label,column in [('all','oriented_excess'),('trend','oriented_conditional_excess')]:
            series=good.groupby('date')[column].mean() if column in good and bias!='neutral' else pd.Series(dtype=float)
            n_valid=int(good[column].notna().sum()) if column in good else 0
            test=block_test(series,calendar,block_size,resamples,one_sided=True) if inference and n_valid>=30 else dict(mean=series.mean(),low=np.nan,high=np.nan,p=np.nan,n_dates=int(series.notna().sum()))
            for key,val in test.items():row[f'{label}_{key}']=val
        if 'direction_hit' in good:
            row['direction_hit_rate']=good.direction_hit.mean()
            row['baseline_direction_rate']=good.baseline_hit.mean()
            row['trend_baseline_direction_rate']=good.conditional_baseline_hit.mean()
            row['direction_hit_gap']= (good.direction_hit-good.baseline_hit).mean()
            row['trend_direction_hit_gap']=(good.direction_hit-good.conditional_baseline_hit).mean()
        extra.append(row)
    result=result.merge(pd.DataFrame(extra),on=['Mẫu hình','Số phiên'])
    result['q BY']=fdr_by(result['p bootstrap'])
    return result


def execution_stress(outcomes,slippages=(0,10,20)):
    """Kịch bản long giả định; không coi OHLC một giá/thiếu KL là đã khớp.

    Slippage là tổng hai chiều, chia đều mua/bán, cộng với phí đã có trong net.
    Không kiểm định thêm để lựa chọn kịch bản có p đẹp.
    """
    if any(not 0<=s<10000 for s in slippages):raise ValueError('Slippage phải từ 0 đến dưới 10000 bps')
    rows=[]
    for keys,g in outcomes.groupby(['name_vi','horizon','fee_bps']):
        valid=g[g.status.eq('evaluated')]
        liquid=(np.isfinite(valid.entry_volume)&valid.entry_volume.gt(0)&
                np.isfinite(valid.exit_volume)&valid.exit_volume.gt(0)&
                ~valid.entry_one_price.eq(True)&~valid.exit_one_price.eq(True))
        feasible=valid[liquid]
        for slip in slippages:
            fraction=slip/20000
            net=(1+feasible.net)*(1-fraction)/(1+fraction)-1
            mae=(1+feasible.mae)/(1+fraction)-1
            rows.append(dict(name_vi=keys[0],horizon=int(keys[1]),fee_bps=keys[2],slippage_bps=slip,
                n_price_evaluated=len(valid),n_execution_eligible=len(feasible),
                n_not_assumed_fill=len(valid)-len(feasible),
                mean_net_pct=net.mean()*100,net_win_rate=float(net.gt(0).mean()) if len(net) else np.nan,
                mean_mae_pct=mae.mean()*100))
    return pd.DataFrame(rows,columns=['name_vi','horizon','fee_bps','slippage_bps','n_price_evaluated',
        'n_execution_eligible','n_not_assumed_fill','mean_net_pct','net_win_rate','mean_mae_pct'])
