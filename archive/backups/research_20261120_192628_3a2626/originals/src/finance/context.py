"""Bối cảnh và kịch bản minh bạch, chỉ dùng nến đã biết tại ngày phân tích."""
import numpy as np
import pandas as pd
from finance.patterns import pattern_catalog, detect_patterns


def signal_context(frame, event, asof, market_days):
    day = pd.Timestamp(event['date'])
    data = frame.loc[frame.index <= pd.Timestamp(asof)].sort_index()
    history = data.loc[data.index <= day]
    if day not in history.index:
        raise ValueError('Thiếu nến tín hiệu')
    bar = history.loc[day]
    info = pattern_catalog().set_index('name').loc[event['name']]
    prior = history.iloc[:-int(info.candles)]
    trend = np.nan if len(prior) < 6 else (prior.close.iloc[-1] / prior.close.iloc[-6] - 1) * 100
    reference = history.iloc[:-1].tail(20)
    volume_mean = reference.volume.mean() if len(reference) == 20 else np.nan
    ratio = bar.volume / volume_mean if pd.notna(volume_mean) and volume_mean > 0 else np.nan
    ema20 = history.close.ewm(span=20, adjust=False, min_periods=20).mean().iloc[-1]
    ema50 = history.close.ewm(span=50, adjust=False, min_periods=50).mean().iloc[-1]
    support = reference.low.min() if len(reference) == 20 else np.nan
    resistance = reference.high.max() if len(reference) == 20 else np.nan
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
    return dict(trend_pct=trend, ema20=ema20, ema50=ema50, volume_ratio=ratio,
                support=support, resistance=resistance, high=float(bar.high), low=float(bar.low),
                close=float(bar.close), status=status, follow=follow,
                invalidation=float(bar.low if bias == 'bullish' else bar.high) if bias != 'neutral' else np.nan)
