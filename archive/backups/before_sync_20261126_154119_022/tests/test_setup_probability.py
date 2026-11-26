import math
from types import SimpleNamespace

import pandas as pd
import pytest

import analytics.setup_probability as module
from analytics.setup_probability import wilson_interval, summarize_setups, build_setup_outcomes


def test_wilson_khong_co_quan_sat():
    low, high = wilson_interval(0, 0)
    assert math.isnan(low) and math.isnan(high)


def test_wilson_gia_tri_da_biet():
    low, high = wilson_interval(5, 10)
    assert low == pytest.approx(0.23659309)
    assert high == pytest.approx(0.76340691)


def test_pending_va_thieu_du_lieu_khong_tinh_la_that_bai():
    outcomes = pd.DataFrame({
        "setup": ["morning_star_setup"] * 4,
        "status": ["completed", "not_completed", "pending", "missing_next_bar"],
    })
    row = summarize_setups(outcomes).iloc[0]
    assert row.n_total == 4
    assert row.n_evaluated == 2
    assert row.n_completed == 1
    assert row.n_pending == row.n_excluded == 1
    assert row.probability == 0.5


def test_khong_co_setup_tra_nan():
    empty = pd.DataFrame(columns=["setup", "status"])
    summary = summarize_setups(empty)
    assert len(summary) == 2
    assert summary.probability.isna().all()


@pytest.mark.parametrize("case,expected", [
    ("completed", "completed"),
    ("not_completed", "not_completed"),
    ("missing", "missing_next_bar"),
    ("invalid", "invalid_next_bar"),
    ("pending", "pending"),
])
def test_xac_nhan_dung_phien_tiep_theo(monkeypatch, case, expected):
    friday, monday, tuesday = pd.to_datetime(["2026-11-13", "2026-11-16", "2026-11-17"])
    dates = pd.DatetimeIndex([friday, monday, tuesday])
    frame = pd.DataFrame({"open": 100., "high": 102., "low": 99., "close": 101.}, index=dates)
    setup_date = tuesday if case == "pending" else friday
    # Cố định đầu ra nhận diện để kiểm tra riêng quy tắc ghép phiên và mẫu số.
    events = pd.DataFrame([
        ("FPT", setup_date, "morning_star_setup", "setup"),
        ("FPT", monday if case == "completed" else tuesday, "morning_star", "pattern"),
    ], columns=["symbol", "date", "name", "kind"])
    monkeypatch.setattr(module, "build_radar", lambda *args: SimpleNamespace(events=events, market_days=dates))
    if case == "missing": frame = frame.drop(monday)
    if case == "invalid": frame.loc[monday, "high"] = 1.
    outcomes = build_setup_outcomes({"FPT": frame}, tuesday)
    assert outcomes.iloc[0].status == expected
    if case != "pending": assert outcomes.iloc[0].next_date == monday
