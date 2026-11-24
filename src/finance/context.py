"""Bối cảnh và kịch bản minh bạch, chỉ dùng nến đã biết tại ngày phân tích."""
import numpy as np
import pandas as pd
from finance.indicators import indicators
from finance.patterns import pattern_catalog, detect_patterns


def history_at(frame,day,market_days,issues=None,symbol=''):
    """Lịch giá đến day; giữ khoảng thiếu và che nến lỗi trước khi tính chỉ báo."""
    day=pd.Timestamp(day)
    data=frame.loc[frame.index<=day].sort_index()
    if data.empty:return data
    calendar=pd.DatetimeIndex(market_days)
    calendar=calendar[(calendar>=data.index.min())&(calendar<=day)].drop_duplicates().sort_values()
    history=data.reindex(calendar).copy()
    px=history[['open','high','low','close']]
    valid=np.isfinite(px).all(axis=1)&px.gt(0).all(axis=1)&history.high.ge(px[['open','close']].max(axis=1))&history.low.le(px[['open','close']].min(axis=1))
    if 'volume' in history:
        valid &= history.volume.isna()|(np.isfinite(history.volume)&history.volume.ge(0))
    if issues is not None and not issues.empty:
        bad=issues[(issues.symbol==symbol)&issues.severity.eq('error')]
        valid &= ~history.index.isin(pd.to_datetime(bad.trading_date))
    history.loc[~valid,:]=np.nan
    return history


def signal_context(frame, event, asof, market_days, issues=None):
    day = pd.Timestamp(event['date'])
    data = frame.loc[frame.index <= pd.Timestamp(asof)].sort_index()
    if day not in data.index:
        raise ValueError('Thiếu nến tín hiệu')
    history=history_at(data,day,market_days,issues,event['symbol'])
    if day not in history.index or pd.isna(history.loc[day,'close']):raise ValueError('Nến tín hiệu không hợp lệ hoặc không thuộc lịch đã biết')
    bar = history.loc[day]
    info = pattern_catalog().set_index('name').loc[event['name']]
    prior = history.iloc[:-int(info.candles)]
    trend = np.nan if len(prior) < 6 else (prior.close.iloc[-1] / prior.close.iloc[-6] - 1) * 100
    reference = history.iloc[:-1].tail(20)
    volume_mean = reference.volume.mean() if len(reference)==20 and reference.volume.notna().all() else np.nan
    ratio = bar.volume / volume_mean if pd.notna(volume_mean) and volume_mean > 0 else np.nan
    missing=np.flatnonzero(history.close.isna().to_numpy())
    continuous=history.iloc[missing[-1]+1:] if len(missing) else history
    ema20 = continuous.close.ewm(span=20, adjust=False, min_periods=20).mean().iloc[-1]
    ema50 = continuous.close.ewm(span=50, adjust=False, min_periods=50).mean().iloc[-1]
    complete=len(reference)==20 and reference.close.notna().all()
    support = reference.low.min() if complete else np.nan
    resistance = reference.high.max() if complete else np.nan
    bias = event['bias']
    follow = 'Chờ phiên kế tiếp đóng cửa vượt đỉnh nến tín hiệu.' if bias == 'bullish' else 'Chờ phiên kế tiếp đóng cửa dưới đáy nến tín hiệu.' if bias == 'bearish' else 'Quan sát giá thoát vùng đỉnh–đáy; đối chiếu xu hướng trước đó.'
    if event['kind'] == 'setup':
        follow = event.get('confirmation', '') or 'Chờ mẫu hình ba nến được xác nhận theo định nghĩa của đồ án.'
    future = pd.DatetimeIndex(market_days)
    future = future[(future > day) & (future <= pd.Timestamp(asof))]
    status = 'Quan sát' if bias == 'neutral' else 'Chờ xác nhận'
    if len(future) and bias != 'neutral':
        nxt = future[0]
        if nxt not in data.index:
            status = 'Thiếu nến xác nhận'
        else:
            row = data.loc[nxt]
            valid = np.isfinite(row[['open','high','low','close']]).all() and row.low > 0 and row.low <= min(row.open,row.close) and row.high >= max(row.open,row.close)
            volume=row.get('volume',np.nan)
            valid = valid and (pd.isna(volume) or (np.isfinite(volume) and volume>=0))
            if issues is not None and not issues.empty:
                flagged=issues[(issues.symbol==event['symbol'])&(issues.severity=='error')]
                valid = valid and not pd.to_datetime(flagged.trading_date).eq(nxt).any()
            if not valid:
                status = 'Nến xác nhận không hợp lệ'
            elif event['kind'] == 'setup':
                patterns = detect_patterns(data.loc[data.index <= nxt])
                name = event['name'].replace('_setup','')
                status = 'Đã xác nhận' if bool(patterns.loc[nxt,name]) else 'Phiên kế tiếp không xác nhận'
            else:
                confirmed = row.close > bar.high if bias == 'bullish' else row.close < bar.low
                invalid = row.close < bar.low if bias == 'bullish' else row.close > bar.high
                status = 'Mất hiệu lực ở phiên kế tiếp' if invalid else 'Đã xác nhận' if confirmed else 'Phiên kế tiếp không xác nhận'
    trend_stat=indicators(history).trend_t.iloc[-int(info.candles)-1] if len(history)>int(info.candles) else np.nan
    return dict(trend_pct=trend, trend_t=trend_stat, ema20=ema20, ema50=ema50, volume_ratio=ratio,
                context_gaps=int(history.close.tail(50).isna().sum()),
                support=support, resistance=resistance, high=float(bar.high), low=float(bar.low),
                close=float(bar.close), status=status, follow=follow,
                invalidation=float(bar.low if bias == 'bullish' else bar.high) if bias != 'neutral' else np.nan)
