"""Đáp án tính tay, ranh giới thời gian và bảo vệ kết quả của các phân tích bổ sung."""
import importlib.util
import json
from pathlib import Path
import sys
from contextlib import closing

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/research'))
import power_diagnostics as power
import q3_incremental as q3
import calendar_audit as calendar
import compare_robustness as robustness
from _support import output_folder, parent_report, digest, snapshot
from data import db
from analytics.study import training_fingerprint
from finance.candles import Thresholds


def star_series(bullish=True, alarm=True):
    returns = (-1 if bullish else 1) * np.tile([.008, .012], 15)
    c = 100 * np.exp(np.cumsum(returns))
    o = np.r_[100, c[:-1]]
    warm = np.column_stack([o, np.maximum(o, c) + .3, np.minimum(o, c) - .3, c])
    if bullish:
        rows = [[90, 91, 79, 80], [78, 78.8, 77, 78.5] if alarm else [81, 81.8, 80, 81.5], [79, 88, 78, 87]]
    else:
        rows = [[80, 91, 79, 90], [92, 93, 91, 92.5] if alarm else [88, 89, 87, 88.5], [92, 93, 82, 83]]
    return pd.DataFrame(np.vstack([warm, rows]), columns=['open', 'high', 'low', 'close'],
        index=pd.bdate_range('2025-01-01', periods=33))


def test_power_known_normal_se_and_ci_width():
    se = .01
    row = {'Mẫu hình': 'Búa', 'Số phiên': 1, 'fee_bps': 20, 'bias': 'bullish',
        'all_low': -norm.ppf(.975) * se, 'all_high': norm.ppf(.975) * se, 'all_mean': 0.,
        'all_std_error': se, 'trend_low': np.nan, 'trend_high': np.nan}
    details, plans, critical = power.analyze(pd.DataFrame([row]))
    item = details[details.baseline.eq('all')].iloc[0]
    expected = 100 * se * (norm.ppf(.95) + norm.ppf(.8))
    assert item.mde80_unadjusted_ci_width_pct == pytest.approx(expected)
    assert item.mde80_unadjusted_saved_se_pct == pytest.approx(expected)
    assert details[details.baseline.eq('trend')].iloc[0].status == 'no_valid_interval'
    assert set(plans.baseline) == {'all'}
    assert item.mde80_by_rank1_ci_width_pct > expected


def test_by_rank_one_is_not_necessary_for_later_ranks_and_floor_is_correct():
    table = power.thresholds()
    assert table.by_raw_critical.iloc[0] == pytest.approx(.05 / (280 * sum(1 / k for k in range(1, 281))))
    assert table.bootstrap_floor.iloc[0] == 1 / 40000
    assert table.by_raw_critical.iloc[1] == 2 * table.by_raw_critical.iloc[0]
    assert table.by_raw_critical.iloc[0] > table.bootstrap_floor.iloc[0]


@pytest.mark.parametrize('bullish', [True, False])
@pytest.mark.parametrize('alarm', [True, False])
def test_q3_same_third_candle_definition_in_alarm_and_control(bullish, alarm):
    frame = star_series(bullish, alarm)
    result = q3.candidates({'A': frame}, None, frame.index, Thresholds())
    row = result[result.setup_date.eq(frame.index[-2])].iloc[0]
    assert row.arm == ('alarm' if alarm else 'first_candle_only')
    assert row.status == 'completed' and row.outcome == 1
    assert row.setup == ('morning_star_setup' if bullish else 'evening_star_setup')
    changed = frame.copy()
    changed.loc[changed.index[-1], 'close'] = changed.open.iloc[-1]
    changed.loc[changed.index[-1], 'high'] = max(changed.high.iloc[-1], changed.open.iloc[-1])
    new = q3.candidates({'A': changed}, None, changed.index, Thresholds())
    newrow = new[new.setup_date.eq(frame.index[-2])].iloc[0]
    assert newrow.arm == row.arm and newrow.status == 'not_completed'


@pytest.mark.parametrize('status', ['pending', 'missing_next_bar', 'invalid_next_bar'])
def test_q3_unknown_outcomes_are_not_failures(status):
    frame = star_series(); dates = frame.index
    if status == 'pending':
        frame = frame.iloc[:-1]; dates = frame.index
    elif status == 'missing_next_bar':
        frame = frame.iloc[:-1]
    else:
        frame.loc[dates[-1], 'high'] = 1
    result = q3.candidates({'A': frame}, None, dates, Thresholds())
    row = result[result.setup_date.eq(dates[-1] if status == 'pending' else dates[-2])].iloc[0]
    assert row.status == status and pd.isna(row.outcome)


def test_q3_boundary_is_purged_and_train_does_not_consume_test_outcome():
    dates = pd.bdate_range('2025-05-19', periods=4)
    rows = pd.DataFrame({'setup_date': dates[:-1], 'next_date': dates[1:]})
    train, test = q3.split_rows(rows, dates[1])
    assert train.setup_date.tolist() == [dates[0]]
    assert test.setup_date.tolist() == [dates[2]]
    assert dates[1] not in train.setup_date.tolist() + test.setup_date.tolist()


def test_day_blocks_match_literal_circular_resampling_with_partial_final_block():
    dates = pd.bdate_range('2025-01-01', periods=23)
    values = np.arange(46).reshape(23, 2)
    daily = pd.DataFrame(values, index=dates)
    starts = np.random.default_rng(2026).integers(0, 23, size=(5, 4))
    literal = []
    for row in starts:
        indices = ((row[:, None] + np.arange(7)) % 23).reshape(-1)[:23]
        literal.append(values[indices].sum(axis=0))
    actual = np.vstack(list(q3.block_draws(daily, dates, resamples=5, length=7)))
    np.testing.assert_array_equal(actual, literal)


@pytest.mark.parametrize('dates,length', [([], 20), (pd.date_range('2025-01-01', periods=2), 0)])
def test_block_sampling_rejects_empty_calendar_or_zero_length(dates, length):
    with pytest.raises(ValueError):
        list(q3.block_draws(pd.DataFrame(), dates, length=length))


def test_pooled_gap_and_symbol_standardization_have_explicit_different_weights():
    dates = pd.bdate_range('2025-01-01', periods=40)
    rows = []
    for symbol, arm, outcomes in [('A', 'alarm', [1, 1]), ('A', 'first_candle_only', [0]),
            ('B', 'alarm', [0]), ('B', 'first_candle_only', [1, 1, 1]), ('C', 'alarm', [1])]:
        rows += [dict(symbol=symbol, arm=arm, outcome=y, setup_date=dates[i]) for i, y in enumerate(outcomes)]
    part = pd.DataFrame(rows)
    pooled = q3.pooled_comparison(part, dates, resamples=99, block_size=2)
    matched = q3.comparison(part, dates, resamples=99, block_size=2)
    assert pooled['gap_mean'] == pytest.approx(3 / 4 - 3 / 4)
    assert matched['n_alarm_unmatched'] == 1
    assert matched['gap_mean'] == pytest.approx(2 / 3 - 1 / 3)
    assert np.isnan(pooled['gap_low'])  # Too few observations; no manufactured certainty.


def test_bootstrap_constant_gain_has_degenerate_interval_and_no_invented_p_value():
    result = q3.bootstrap_metric(.02, np.repeat(.02, 999), 999, True)
    assert result['low'] == result['high'] == .02
    assert result['low_family'] == result['high_family'] == .02
    assert not any(key in result for key in ['p', 'q'])
    assert np.isnan(q3.bootstrap_metric(.02, [.02] * 5, 999, True)['low'])


def test_q3_forecasts_are_fit_only_from_training_and_scores_are_paired():
    dates = pd.bdate_range('2025-01-01', periods=40)
    name = 'morning_star_setup'
    train = pd.DataFrame([dict(setup=name, arm=arm, outcome=y) for arm, y in
        [('alarm', 1), ('alarm', 0), ('first_candle_only', 0), ('first_candle_only', 0)]])
    test = pd.DataFrame([dict(setup=name, arm='alarm', outcome=y, setup_date=dates[i]) for i, y in enumerate([1, 0])])
    scores, predictions = q3.score_forecasts(train, test, dates, resamples=99, block_size=2)
    row = scores[scores.setup.eq(name)].iloc[0]
    assert row.forecast_alarm == .5 and row.forecast_control == .25
    assert row.brier_gain_mean == pytest.approx(((.25 - 1) ** 2 + .25 ** 2) / 2 - .25)
    test['outcome'] = 1
    new, _ = q3.score_forecasts(train, test, dates, resamples=99, block_size=2)
    assert new.iloc[0].forecast_alarm == row.forecast_alarm
    assert new.iloc[0].forecast_control == row.forecast_control
    assert len(predictions) == 2


@pytest.mark.parametrize('date', ['2024-04-29', '2025-05-02', '2026-01-02', '2026-08-31', '2026-11-24', '2025-04-26'])
def test_final_official_holidays_and_weekend_makeup_days_are_closed(date):
    reference = pd.read_csv(calendar.REFERENCE, parse_dates=['start', 'end'])
    days, _ = calendar.scheduled_days(date, date, reference)
    assert not days.expected_open.iloc[0]


def test_calendar_reports_global_mismatch_and_single_symbol_closed_day_separately():
    reference = pd.read_csv(calendar.REFERENCE, parse_dates=['start', 'end'])
    inferred = pd.to_datetime(['2026-01-05', '2026-01-07'])
    frames = {'IPO': pd.DataFrame(index=pd.to_datetime(['2026-01-06', '2026-01-10']))}
    days, _, bars, _ = calendar.audit(inferred, frames, reference)
    assert days.loc[days.date.eq('2026-01-06'), 'status'].iloc[0] == 'expected_open_missing_from_inferred'
    assert bars.empty  # Saturday lies outside the audited period, not silently counted as a discrepancy.
    inferred = pd.to_datetime(['2026-01-05', '2026-01-10'])
    _, _, bars, _ = calendar.audit(inferred, frames, reference)
    assert bars.to_dict('records') == [dict(symbol='IPO', date=pd.Timestamp('2026-01-10'))]


def test_calendar_does_not_extrapolate_unverified_years():
    reference = pd.read_csv(calendar.REFERENCE, parse_dates=['start', 'end'])
    with pytest.raises(ValueError, match='2021–2026'):
        calendar.scheduled_days('2027-01-01', '2027-01-05', reference)


def load_cli():
    spec = importlib.util.spec_from_file_location('supplement_study_cli', ROOT / 'scripts/run_study.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('options', [['--exclude', 'BSR'], ['--exclude', 'ECO', '--out', 'unused'],
    ['--exclude', ','.join((ROOT / 'src/data/universe_vn30.txt').read_text(encoding='utf-8').split()), '--out', 'unused']])
def test_exclusion_cli_rejects_unsafe_or_unknown_or_empty_universe_before_reading_db(options):
    with pytest.raises(SystemExit) as error:
        load_cli().main(['--db', 'does-not-exist.db'] + options)
    assert error.value.code == 2


def test_exclusion_cannot_overwrite_main_manifest(tmp_path):
    cli = load_cli(); path = tmp_path / 'radar.db'
    symbols = cli.load_universe(ROOT / 'src/data/universe_vn30.txt')
    with closing(db.connect(path)) as connection:
        for symbol in symbols:
            db.upsert_ohlc(connection, symbol, star_series())
    out = tmp_path / 'main'; out.mkdir()
    content = json.dumps(dict(mode='in_sample', universe=symbols))
    (out / 'manifest.json').write_text(content, encoding='utf-8')
    with pytest.raises(ValueError, match='Rổ/loại mã'):
        cli.main(['--db', str(path), '--exclude', 'bsr, MCH, vpl', '--out', str(out)])
    assert (out / 'manifest.json').read_text(encoding='utf-8') == content
    assert sorted(p.name for p in out.iterdir()) == ['manifest.json']


def test_output_and_parent_csv_hash_guards(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    with pytest.raises(ValueError, match='kết quả chính'):
        output_folder(source, source)
    protocol = source / 'oos_protocol.json'; protocol.write_text('{}', encoding='utf-8')
    table = source / 'test.csv'; table.write_text('value\n1\n', encoding='utf-8')
    manifest = dict(status='complete', mode='oos', protocol_sha256=digest(protocol), table_hashes={'test.csv': digest(table)})
    (source / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert parent_report(source)[1] == manifest
    with pytest.raises(ValueError, match='đã có dữ liệu'):
        output_folder(source)
    table.write_text('value\n2\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Bảng nguồn thay đổi'):
        parent_report(source)


def test_snapshot_hash_rejects_revision_but_allows_data_after_frozen_asof(tmp_path):
    path = tmp_path / 'db.sqlite'; frame = star_series(); cut = frame.index[-2]
    with closing(db.connect(path)) as connection:
        db.upsert_ohlc(connection, 'A', frame)
        historical = {'A': db.load_ohlc(connection, 'A').loc[:cut]}
        issues = pd.read_sql_query('SELECT symbol,trading_date,check_name AS "check",severity,detail FROM quality_issues', connection)
    manifest = dict(universe=['A'], asof=str(cut.date()),
        input_snapshot_sha256=training_fingerprint(historical, issues, cut))
    assert len(snapshot(path, manifest)[0]['A']) == len(frame) - 1
    with closing(db.connect(path)) as connection:
        revised = frame.iloc[:1].copy(); revised['volume'] = 1
        db.upsert_ohlc(connection, 'A', revised)
    with pytest.raises(ValueError, match='snapshot khác'):
        snapshot(path, manifest)


@pytest.mark.parametrize('change', ['asof', 'thresholds', 'calendar'])
def test_robustness_comparison_refuses_changed_design_or_calendar(tmp_path, change):
    source = tmp_path / 'main'; source.mkdir()
    reduced = tmp_path / 'reduced'; reduced.mkdir()
    dates = pd.DataFrame({'date': ['2025-05-20', '2025-05-21'], 'partition': ['train', 'test']})
    dates.to_csv(source / 'split_assignments.csv', index=False)
    dates.to_csv(reduced / 'split_assignments.csv', index=False)
    protocol = dict(train_end='2025-05-20', test_start='2025-05-21', horizons=[1, 3, 5, 10, 20],
        fees_bps=[20, 40], thresholds={'doji_k': .1}, resamples=39999, block_size=20, primary_family=280)
    parent = dict(asof='2026-11-16', universe=['A', 'BSR'], protocol=protocol)
    other = dict(asof=parent['asof'], universe=['A'], excluded_symbols=['BSR'], protocol=dict(protocol))
    assert robustness.validate_design(source, parent, reduced, other) == ['BSR']
    if change == 'asof':
        other['asof'] = '2026-11-17'
    elif change == 'thresholds':
        other['protocol']['thresholds'] = {'doji_k': .2}
    else:
        dates.loc[1, 'date'] = '2025-05-22'
        dates.to_csv(reduced / 'split_assignments.csv', index=False)
    with pytest.raises((ValueError, AssertionError)):
        robustness.validate_design(source, parent, reduced, other)
