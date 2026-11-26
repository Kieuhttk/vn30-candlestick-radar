"""Nến tự dựng: hình dạng, xu hướng trước mẫu hình và ngày xác nhận."""
import numpy as np
import pandas as pd
import pytest

from finance.candles import Thresholds
from finance.patterns import detect_patterns,detect_setups,to_events


def series(rows,trend='down'):
    direction=-1 if trend=='down' else 1
    returns=direction*np.tile([.008,.012],15)
    close=100*np.exp(np.cumsum(returns));opening=np.r_[100,close[:-1]]
    warm=np.column_stack([opening,np.maximum(opening,close)+.3,
        np.minimum(opening,close)-.3,close])
    values=np.vstack([warm,np.array(rows,dtype=float)])
    return pd.DataFrame(values,columns=['open','high','low','close'],
        index=pd.bdate_range('2025-01-01',periods=len(values)))


@pytest.mark.parametrize('name,trend,row',[
    ('hammer','down',[80,81.2,75,81]),('hanging_man','up',[80,81.2,75,81]),
    ('inverted_hammer','down',[80,86,79.8,81]),('shooting_star','up',[80,86,79.8,81])])
def test_one_candle_reversals_require_the_corresponding_prior_trend(name,trend,row):
    assert detect_patterns(series([row],trend)).iloc[-1][name]
    opposite='up' if trend=='down' else 'down'
    assert not detect_patterns(series([row],opposite)).iloc[-1][name]


@pytest.mark.parametrize('name,row',[
    ('dragonfly_doji',[100,100.1,95,100]),('gravestone_doji',[100,105,99.9,100]),
    ('long_legged_doji',[100,103,97,100]),('marubozu_white',[100,110,100,110]),
    ('marubozu_black',[110,110,100,100]),('spinning_top',[100,103,97,101])])
def test_neutral_and_marubozu_shapes_with_known_geometry(name,row):
    frame=pd.DataFrame([[100,102,98,101]]*20+[row],columns=['open','high','low','close'],
        index=pd.bdate_range('2025-01-01',periods=21))
    last=detect_patterns(frame).iloc[-1]
    assert last[name]
    if 'doji' in name:assert last.doji


@pytest.mark.parametrize('name,trend,rows',[
    ('bullish_engulfing','down',[[90,91,79,80],[79,93,78,92]]),
    ('bearish_engulfing','up',[[80,91,79,90],[91,92,77,78]]),
    ('bullish_harami','down',[[90,91,79,80],[82,87,81,86]]),
    ('bearish_harami','up',[[80,91,79,90],[88,89,83,84]])])
def test_two_candle_patterns_are_attached_to_the_final_candle(name,trend,rows):
    signals=detect_patterns(series(rows,trend))
    assert not signals.iloc[-2][name] and signals.iloc[-1][name]
    assert not detect_patterns(series(rows,'up' if trend=='down' else 'down')).iloc[-1][name]


@pytest.mark.parametrize('name,trend,rows',[
    ('piercing','down',[[90,91,79,80],[79.5,87,79,86]]),
    ('dark_cloud_cover','up',[[80,91,79,90],[90.5,91,83,84]])])
def test_strict_gap_rejects_a_gap_only_beyond_previous_close(name,trend,rows):
    frame=series(rows,trend)
    assert detect_patterns(frame).iloc[-1][name]
    assert not detect_patterns(frame,Thresholds(strict_gap=True)).iloc[-1][name]


@pytest.mark.parametrize('name,trend,rows',[
    ('morning_star','down',[[90,91,79,80],[78,78.8,77,78.5],[79,88,78,87]]),
    ('evening_star','up',[[80,91,79,90],[92,93,91,92.5],[92,93,82,83]])])
def test_star_setup_precedes_completion_and_midpoint_is_strict(name,trend,rows):
    frame=series(rows,trend);setup=name+'_setup'
    assert detect_setups(frame.iloc[:-1]).iloc[-1][setup]
    assert not detect_patterns(frame.iloc[:-1]).iloc[-1][name]
    assert detect_patterns(frame).iloc[-1][name]
    boundary=frame.copy();boundary.loc[boundary.index[-1],'close']=85
    assert not detect_patterns(boundary).iloc[-1][name]
    # Nến thứ ba không sửa cảnh báo đã tồn tại ở nến thứ hai.
    assert detect_setups(boundary).iloc[-2][setup]


def test_one_price_bar_is_neither_a_pattern_nor_a_setup():
    frame=series([[80,80,80,80]])
    assert not detect_patterns(frame).iloc[-1].any()
    assert not detect_setups(frame).iloc[-1].any()


def test_detection_is_prefix_invariant_and_events_keep_date_direction():
    frame=series([[90,91,79,80],[79,93,78,92],[92,95,91,94]])
    expected=detect_patterns(frame.iloc[:-1]);setups=detect_setups(frame.iloc[:-1])
    frame.iloc[-1]*=20
    pd.testing.assert_frame_equal(expected,detect_patterns(frame).iloc[:-1])
    pd.testing.assert_frame_equal(setups,detect_setups(frame).iloc[:-1])
    events=to_events(expected[['bullish_engulfing']])
    assert events.to_dict('records')==[{'date':frame.index[-2],'pattern':'bullish_engulfing',
        'bias':'bullish','candles':2}]
