"""Đối chiếu lịch đã khóa với lịch nghỉ công bố; không sửa lịch hay SQLite."""
from pathlib import Path
import argparse
import pandas as pd
from _support import ROOT, parent_report, snapshot, output_folder, csv, finish, digest, utf8

REFERENCE = ROOT / 'scripts/research/reference/vn_market_holidays_2021_2026.csv'
COVERAGE_START = pd.Timestamp('2021-01-01')
COVERAGE_END = pd.Timestamp('2026-12-31')


def scheduled_days(start, end, reference):
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if start < COVERAGE_START or end > COVERAGE_END or end < start:
        raise ValueError('Lịch tham chiếu chỉ được đối chiếu cho giai đoạn 2021–2026')
    years = set(range(start.year, end.year + 1))
    if not years.issubset(set(pd.to_datetime(reference.start).dt.year)):
        raise ValueError('Thiếu năm trong tài liệu lịch nghỉ')
    holidays = []
    for row in reference.itertuples(index=False):
        for day in pd.date_range(row.start, row.end):
            if start <= day <= end:
                holidays.append(dict(date=day, holiday=row.holiday, source_url=row.source_url,
                    exchange_reference=row.exchange_reference, verified_on=row.verified_on))
    expanded = pd.DataFrame(holidays, columns=['date', 'holiday', 'source_url', 'exchange_reference', 'verified_on'])
    days = pd.date_range(start, end)
    result = pd.DataFrame({'date': days})
    result['weekend'] = days.dayofweek >= 5
    result['announced_holiday'] = days.isin(expanded.date)
    result['expected_open'] = ~result.weekend & ~result.announced_holiday
    return result, expanded


def audit(inferred, frames, reference):
    inferred = pd.DatetimeIndex(inferred).normalize().sort_values()
    if inferred.empty or inferred.has_duplicates:
        raise ValueError('Lịch nguồn phải có các ngày duy nhất và không rỗng')
    result, holidays = scheduled_days(inferred.min(), inferred.max(), reference)
    result['inferred_open'] = result.date.isin(inferred)
    result['status'] = 'matched_closed'
    result.loc[result.expected_open & result.inferred_open, 'status'] = 'matched_open'
    result.loc[result.expected_open & ~result.inferred_open, 'status'] = 'expected_open_missing_from_inferred'
    result.loc[~result.expected_open & result.inferred_open, 'status'] = 'inferred_on_announced_closed_day'
    closed = set(result.loc[~result.expected_open, 'date'])
    bars = pd.DataFrame([dict(symbol=s, date=d) for s, f in frames.items() for d in f.index
        if d.normalize() in closed], columns=['symbol', 'date'])
    result['year'] = result.date.dt.year
    summary = result.groupby('year').agg(calendar_days=('date', 'size'),
        expected_sessions=('expected_open', 'sum'), inferred_sessions=('inferred_open', 'sum'))
    mismatch = result.status.str.contains('missing|inferred_on')
    summary['mismatches'] = mismatch.groupby(result.year).sum()
    return result, holidays, bars, summary.reset_index()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', default='report/oos_verified')
    parser.add_argument('--db', default='storage/radar.db')
    parser.add_argument('--reference', default=str(REFERENCE))
    parser.add_argument('--out', default='report/supplement_20261124/calendar')
    args = parser.parse_args()
    source, manifest = parent_report(args.study)
    frames, _ = snapshot(args.db, manifest)
    reference = pd.read_csv(args.reference, parse_dates=['start', 'end'])
    inferred = pd.read_csv(source / 'split_assignments.csv', parse_dates=['date']).date
    days, holidays, bars, summary = audit(inferred, frames, reference)
    out = output_folder(args.out, source)
    for name, table in [('calendar_days.csv', days), ('expanded_holidays.csv', holidays),
                        ('bars_on_closed_days.csv', bars), ('calendar_by_year.csv', summary)]:
        csv(out, name, table)
    finish(out, 'official_holiday_calendar_audit', source, dict(
        reference_sha256=digest(args.reference), reference_coverage=['2021-01-01', '2026-12-31'],
        checked_from=str(inferred.min().date()), checked_to=str(inferred.max().date()),
        source_scope='VSD/VSDC settlement notices corroborated by HNX/HOSE trading notices',
        cautions=['holiday cross-check, not a complete registry of unscheduled exchange halts',
                  'historical notices collected retrospectively on 2026-11-24',
                  'an individual symbol missing a bar does not redefine the market calendar',
                  'no Saturday makeup trading assumed; government workdays are not trading sessions']), __file__)
    print(summary.to_string(index=False))
    print('Bars on scheduled closed days:', len(bars))


if __name__ == '__main__':
    utf8()
    main()
