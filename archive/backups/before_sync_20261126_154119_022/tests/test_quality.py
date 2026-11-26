"""Phân biệt lỗi phải loại, cảnh báo giữ lại và đối chiếu hai nguồn."""
import numpy as np
import pandas as pd
import pytest

from data.quality import (check_ohlc,check_cross,check_calendar,check_freshness,
    ex_event_mask,split_valid)


def bars():
    return pd.DataFrame(dict(open=100.,high=102.,low=98.,close=101.,volume=1000.),
        index=pd.bdate_range('2026-01-05',periods=4))


@pytest.mark.parametrize('column,value,check,severity',[
    ('close',np.inf,'non_positive_price','error'),('low',0.,'non_positive_price','error'),
    ('high',99.,'inconsistent_ohlc','error'),('volume',-1.,'negative_volume','error'),
    ('volume',np.inf,'non_finite_volume','error'),('volume',np.nan,'missing_volume','warning'),
    ('volume',0.,'zero_volume','warning')])
def test_invalid_prices_and_volume_have_the_correct_disposition(column,value,check,severity):
    frame=bars();frame.loc[frame.index[1],column]=value
    issues=check_ohlc(frame,'FPT')
    assert ((issues['check']==check)&(issues.severity==severity)&
        (issues.trading_date=='2026-01-06')&(issues.symbol=='FPT')).any()


def test_cross_source_comparison_reports_both_missing_dates_and_value_mismatch():
    original=bars();other=original.rename(columns={'volume':'total_match'}).copy()
    other.loc[other.index[1],'close']=102;other.loc[other.index[1],'total_match']=1500
    issues=check_cross(original.iloc[:-1],other.iloc[1:],'FPT')
    assert set(issues['check'])=={'missing_in_summary','missing_in_ohlc',
        'cross_mismatch_close','cross_mismatch_volume'}
    assert issues.severity.eq('warning').all()


def test_split_valid_drops_errors_only_and_keeps_last_duplicate_sorted():
    frame=bars();last=frame.iloc[:1].copy();last['close']=102
    frame=pd.concat([frame.iloc[::-1],last])
    issues=pd.DataFrame([dict(trading_date='2026-01-06',severity='error'),
        dict(trading_date='2026-01-05',severity='warning')])
    clean,rejected=split_valid(frame,issues)
    assert clean.index.is_monotonic_increasing and clean.index.is_unique
    assert clean.iloc[0].close==102 and len(clean)==3
    assert rejected.index.tolist()==[pd.Timestamp('2026-01-06')]


def test_calendar_flags_internal_missing_session_but_not_prelisting_days():
    full=bars();frames={'ACB':full,'FPT':full.drop(full.index[2]),'NEW':full.iloc[1:]}
    issues=check_calendar(frames)
    assert issues[['symbol','trading_date','check']].to_dict('records')==[
        dict(symbol='FPT',trading_date='2026-01-07',check='missing_session')]


def test_reference_change_is_a_flag_not_a_forced_price_correction():
    frame=bars();frame['ref']=[100,101,90,101];before=frame.copy(deep=True)
    assert ex_event_mask(frame).tolist()==[False,False,True,False]
    assert not ex_event_mask(frame.drop(columns='ref')).any()
    pd.testing.assert_frame_equal(frame,before)


@pytest.mark.parametrize('last,expected',[(None,'no_data'),(pd.NaT,'no_data'),
    (pd.Timestamp('2026-01-01'),'stale_data')])
def test_freshness_handles_missing_dates_and_old_history(last,expected):
    issues=check_freshness(last,today='2026-01-10',symbol='FPT')
    assert issues.iloc[0]['check']==expected
    assert issues.iloc[0].severity==('error' if expected=='no_data' else 'warning')
