"""Đáp án OHLC tính tay và hợp đồng dữ liệu của lớp mô tả nến."""
import numpy as np
import pandas as pd
import pytest

from finance.candles import Thresholds, describe_candles, validate_ohlc


def sample():
    return pd.DataFrame([[100,106,98,104],[105,107,100,102],[101,104,99,101]],
        columns=['open','high','low','close'],index=pd.bdate_range('2026-01-05',periods=3),dtype=float)


def test_geometry_and_prior_averages_by_hand_without_mutating_input():
    frame=sample();before=frame.copy(deep=True)
    out=describe_candles(frame,Thresholds(avg_window=2))
    np.testing.assert_allclose(out.body,[4,3,0])
    np.testing.assert_allclose(out.rng,[8,7,5])
    np.testing.assert_allclose(out.upper,[2,2,3])
    np.testing.assert_allclose(out.lower,[2,2,2])
    assert out.white.tolist()==[True,False,False]
    assert out.black.tolist()==[False,True,False]
    assert out.iloc[2].body_avg==3.5 and out.iloc[2].range_avg==7.5
    assert not out.doji.iloc[:2].any() and out.doji.iloc[2]
    pd.testing.assert_frame_equal(frame,before)


@pytest.mark.parametrize('case',['missing_column','unsorted','duplicate','nan','infinite_high',
    'infinite_close','zero_price','negative_price','bad_high','bad_low'])
def test_invalid_ohlc_is_rejected_before_classification(case):
    frame=sample()
    if case=='missing_column':frame=frame.drop(columns='low')
    elif case=='unsorted':frame=frame.iloc[::-1]
    elif case=='duplicate':frame.index=[frame.index[0],frame.index[0],frame.index[2]]
    else:
        column,value={'nan':('open',np.nan),'infinite_high':('high',np.inf),
            'infinite_close':('close',np.inf),'zero_price':('low',0),
            'negative_price':('low',-1),'bad_high':('high',99),'bad_low':('low',105)}[case]
        frame.loc[frame.index[0],column]=value
    with pytest.raises(ValueError):validate_ohlc(frame)


def test_one_price_bar_has_no_shape_or_infinite_ratios():
    frame=sample();frame.loc[frame.index[-1],:]=100
    row=describe_candles(frame,Thresholds(avg_window=2)).iloc[-1]
    assert row.rng==0 and not row.doji and not row.long_body and not row.short_body
    assert row[['body_pct','upper_pct','lower_pct']].isna().all()


def test_reference_alignment_gap_and_limit_flags_by_hand():
    frame=sample();ref=pd.Series([100,110,96],index=frame.index[::-1])
    result=describe_candles(frame,ref=ref)
    assert result.iloc[0].gap==pytest.approx(100/96-1)
    assert result.iloc[0].ret_ref==pytest.approx(104/96-1)
    assert result.iloc[0].limit_up and result.iloc[1].limit_down


def test_future_prices_cannot_change_past_descriptions():
    frame=sample()
    frame=pd.DataFrame(np.tile(frame.to_numpy(),(10,1)),columns=frame.columns,
        index=pd.bdate_range('2026-01-05',periods=30))
    cut=frame.index[19]
    expected=describe_candles(frame.loc[:cut])
    frame.loc[frame.index>cut,:]*=50
    pd.testing.assert_frame_equal(expected,describe_candles(frame).loc[:cut])


@pytest.mark.parametrize('settings',[{'avg_window':1},{'trend_window':2}])
def test_insufficient_threshold_windows_are_rejected(settings):
    with pytest.raises(ValueError):Thresholds(**settings)
