"""So sánh nghiên cứu loại mã với kết quả chính; không chọn lại kết quả chính."""
import argparse
import json
import pandas as pd
from _support import parent_report, output_folder, csv, finish, digest, utf8


def validate_design(source, parent, other, reduced):
    if parent['asof'] != reduced['asof']:
        raise ValueError('Phải dùng cùng ngày chốt để so sánh loại mã')
    for key in ['train_end', 'test_start', 'horizons', 'fees_bps', 'thresholds',
                'resamples', 'block_size', 'primary_family']:
        if parent['protocol'][key] != reduced['protocol'][key]:
            raise ValueError('Thiết kế khác ở ' + key)
    removed = sorted(set(parent['universe']) - set(reduced['universe']))
    if not removed or not set(reduced['universe']) < set(parent['universe']):
        raise ValueError('Rổ độ vững phải là tập con thực sự của rổ chính')
    if removed != sorted(reduced.get('excluded_symbols', [])):
        raise ValueError('Danh sách loại mã không khớp manifest')
    left = pd.read_csv(source / 'split_assignments.csv')
    right = pd.read_csv(other / 'split_assignments.csv')
    pd.testing.assert_frame_equal(left, right)
    return removed


def compare_q2(original, reduced):
    keys = ['Mẫu hình', 'Số phiên', 'fee_bps', 'bias']
    metrics = ['Tổng nhãn', 'Đủ dữ liệu', 'Long sau phí TB (%)',
               'all_mean', 'trend_mean', 'all_p', 'trend_p', 'all_q_fixed', 'trend_q_fixed']
    result = original[keys + metrics].merge(reduced[keys + metrics], on=keys,
        suffixes=('_main', '_excluded'), validate='one_to_one', how='outer', indicator=True)
    if not result._merge.eq('both').all():
        raise ValueError('Họ giả thuyết không khớp')
    return result.drop(columns='_merge')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', default='report/oos_verified')
    parser.add_argument('--excluded-study', default='report/supplement_20261124/exclude_oos')
    parser.add_argument('--out', default='report/supplement_20261124/exclusion_comparison')
    args = parser.parse_args()
    source, parent = parent_report(args.study)
    other, reduced = parent_report(args.excluded_study)
    removed = validate_design(source, parent, other, reduced)
    out = output_folder(args.out, source)
    q2 = compare_q2(pd.read_csv(source / 'q2_oos_summary.csv'), pd.read_csv(other / 'q2_oos_summary.csv'))
    csv(out, 'q2_exclusion_comparison.csv', q2)
    q3 = pd.read_csv(source / 'q3_oos_summary.csv').merge(pd.read_csv(other / 'q3_oos_summary.csv'),
        on=['setup', 'name_vi'], suffixes=('_main', '_excluded'), validate='one_to_one')
    csv(out, 'q3_exclusion_comparison.csv', q3)
    years = []
    for part in ['train', 'oos']:
        name = f'q1_{part}_pattern_year.csv'
        for label, folder in [('main', source), ('excluded', other)]:
            table = pd.read_csv(folder / name, index_col=0)
            for pattern, row in table.iterrows():
                for year, n in row.items():
                    years.append(dict(partition=part, version=label, pattern=pattern, year=year, n=n))
    csv(out, 'q1_exclusion_counts.csv', pd.DataFrame(years))
    rows = []
    for label, folder, manifest in [('main', source, parent), ('excluded', other, reduced)]:
        table = pd.read_csv(folder / 'q2_oos_summary.csv')
        pvalues = pd.concat([table.all_p, table.trend_p]).dropna()
        qvalues = pd.concat([table.all_q_fixed, table.trend_q_fixed]).dropna()
        rows.append(dict(version=label, n_symbols=len(manifest['universe']),
            primary_family=manifest['planned_directional_family'], n_finite_p=len(pvalues),
            minimum_raw_p=pvalues.min(), minimum_q=qvalues.min(), n_q_below_05=int((qvalues < .05).sum()),
            n_test_signals=len(pd.read_csv(folder / 'signals_oos.csv'))))
    csv(out, 'exclusion_summary.csv', pd.DataFrame(rows))
    finish(out, 'separate_exclusion_robustness', source, dict(excluded_symbols=removed,
        reduced_manifest_sha256=digest(other / 'manifest.json'), same_calendar=True,
        main_numerical_hashes=parent['protocol']['numerical_code_hashes'],
        reduced_numerical_hashes=reduced['protocol']['numerical_code_hashes'],
        cautions=['robustness analysis, does not replace primary results',
                  'removes complete histories of three prespecified symbols, not point-in-time membership',
                  'reduced protocol is stored separately; pre-existing candle validation hash change is disclosed']), __file__)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == '__main__':
    utf8()
    main()
