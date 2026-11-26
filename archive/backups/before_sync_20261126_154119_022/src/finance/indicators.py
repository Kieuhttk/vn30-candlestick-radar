"""Chỉ báo chỉ dùng dữ liệu đã biết tại từng ngày; không có I/O."""
import numpy as np
import pandas as pd


def indicators(frame, trend_window=10):
    c=frame.close.astype(float);r=np.log(c/c.shift(1));volume=frame.volume.astype(float)
    prior=volume.rolling(20,min_periods=20).mean().shift(1)
    sd=volume.rolling(20,min_periods=20).std().shift(1)
    return pd.DataFrame({'ema20':c.ewm(span=20,adjust=False,min_periods=20).mean(),
        'ema50':c.ewm(span=50,adjust=False,min_periods=50).mean(),
        'volume_z20':(volume-prior)/sd.replace(0,np.nan),
        'volatility20':r.rolling(20,min_periods=20).std()*np.sqrt(252),
        'trend_t':r.rolling(trend_window).mean()/r.rolling(trend_window).std()*np.sqrt(trend_window)},index=frame.index)
