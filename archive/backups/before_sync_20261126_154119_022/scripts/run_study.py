"""Tái lập Q1–Q3: toàn lịch sử hoặc holdout theo thời gian, chỉ đọc SQLite."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import argparse
import hashlib
import json
import platform
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from data import db
from data.ingest import load_universe
from finance.candles import Thresholds
from analytics.radar import build_radar
from analytics.event_study import execution_stress
from data.quality import last_closed_day
from analytics.setup_probability import build_setup_outcomes, summarize_setups
from analytics.study import (q1_tables, q2_tables, sensitivity_tables, HORIZONS, FEES,
                             make_oos_protocol, training_fingerprint, oos_tables)


def source_hashes():
    paths = [p for folder in ['src/analytics', 'src/finance', 'src/data']
             for p in (ROOT / folder).glob('*.py')] + [Path(__file__)]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def numerical_hashes():
    paths = ['src/analytics/' + p for p in ['event_study.py', 'study.py', 'radar.py',
             'setup_probability.py', 'inference.py', 'multiple_testing.py']]
    paths += ['src/finance/candles.py', 'src/finance/patterns.py','src/data/quality.py']
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


def save_csv(out, name, frame, index=False):
    temp = out / (name + '.tmp')
    try:
        frame.to_csv(temp, index=index, encoding='utf-8-sig')
        temp.replace(out / name)
    finally:
        temp.unlink(missing_ok=True)
    print(name, frame.shape, flush=True)


def locked_protocol(out, frames, issues, asof, args):
    path = out / 'oos_protocol.json'
    if path.exists():
        protocol = json.loads(path.read_text(encoding='utf-8'))
        if args.train_end is not None and pd.Timestamp(args.train_end).normalize() != pd.Timestamp(protocol['train_end']):
            raise ValueError('Mốc train đã khóa; dùng đúng mốc cũ hoặc thư mục --out mới cho nghiên cứu khác')
        if args.train_fraction is not None and args.train_fraction != protocol['requested_train_fraction']:
            raise ValueError('Tỷ lệ chia đã khóa trong oos_protocol.json')
        expected = dict(universe=sorted(frames), horizons=list(HORIZONS), fees_bps=list(FEES),
                        thresholds=asdict(Thresholds()), resamples=args.resamples,
                        block_size=args.block_size, numerical_code_hashes=numerical_hashes(),
                        numerical_libraries={'numpy':np.__version__,'pandas':pd.__version__})
        for key, value in expected.items():
            if protocol.get(key) != value:
                raise ValueError(f'Protocol đã khóa nhưng {key} thay đổi; không ghi đè kết quả. Dùng cấu hình cũ hoặc --out mới')
        if pd.Timestamp(asof) < pd.Timestamp(protocol['test_start']):
            raise ValueError('Ngày đánh giá đứng trước tập test đã khóa')
        actual = training_fingerprint(frames, issues, protocol['train_end'])
        if actual != protocol['training_input_sha256']:
            raise ValueError('Dữ liệu train đã thay đổi (có thể API điều chỉnh lịch sử). Cần nghiên cứu phiên bản mới, không tự fit lại vào protocol cũ')
    else:
        protocol, _ = make_oos_protocol(frames, asof,
            train_fraction=.7 if args.train_fraction is None else args.train_fraction,
            train_end=args.train_end)
        protocol.update(resamples=args.resamples, block_size=args.block_size, seed=2026,
            numerical_code_hashes=numerical_hashes(),
            numerical_libraries={'numpy':np.__version__,'pandas':pd.__version__},
            training_input_sha256=training_fingerprint(frames, issues, protocol['train_end']),
            created_at=datetime.now(db.VN).isoformat())
        path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding='utf-8')
    return protocol


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='storage/radar.db')
    parser.add_argument('--asof')
    parser.add_argument('--out', help='Mặc định report/tables; --oos dùng report/oos_verified')
    parser.add_argument('--sensitivity', action='store_true')
    parser.add_argument('--resamples', type=int, default=39999)
    parser.add_argument('--block-size', type=int, default=20)
    parser.add_argument('--oos', action='store_true', help='70%% phiên đầu fit, 30%% phiên cuối đánh giá; khóa protocol')
    parser.add_argument('--train-fraction', type=float, default=None)
    parser.add_argument('--train-end', help='Mốc train YYYY-MM-DD thay cho tỷ lệ; giữ cố định khi nạp thêm dữ liệu')
    parser.add_argument('--exclude',default='',help='Mã loại trong kiểm tra độ vững, phân cách bằng dấu phẩy; yêu cầu --out riêng')
    args = parser.parse_args(argv)
    if args.resamples < 99 or args.block_size < 1:
        parser.error('--resamples >= 99 và --block-size >= 1')
    if not args.oos and (args.train_fraction is not None or args.train_end is not None):
        parser.error('--train-fraction/--train-end yêu cầu --oos')
    excluded=sorted({s.strip().upper() for s in args.exclude.split(',') if s.strip()})
    if excluded and not args.out:parser.error('--exclude yêu cầu --out riêng để giữ nguyên kết quả chính')
    path = Path(args.db)
    path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    symbols = list(dict.fromkeys(load_universe(ROOT / 'src/data/universe_vn30.txt')))
    if len(symbols) != 30:
        raise ValueError('Luồng báo cáo yêu cầu rổ cố định 30 mã; kiểm tra universe_vn30.txt')
    full_universe=list(symbols)
    unknown=set(excluded)-set(symbols)
    if unknown:parser.error('Mã --exclude ngoài rổ: '+', '.join(sorted(unknown)))
    symbols=[s for s in symbols if s not in excluded]
    if not symbols:parser.error('--exclude không được loại toàn bộ rổ')
    with closing(db.connect_readonly(path)) as conn:
        conn.execute('BEGIN')
        frames = {s: db.load_ohlc(conn, s) for s in symbols}
        issues = pd.read_sql_query('SELECT symbol,trading_date,check_name AS "check",severity,detail FROM quality_issues', conn)
    empty = [s for s, f in frames.items() if f.empty]
    if empty:
        raise ValueError('Thiếu toàn bộ OHLC cho mã trong rổ cố định: ' + ', '.join(empty))
    now = datetime.now(db.VN)
    closed = last_closed_day(now)
    latest = max(f.index.max() for f in frames.values() if not f.empty)
    asof = pd.Timestamp(args.asof).normalize() if args.asof else min(latest, closed)
    if asof > closed:
        raise ValueError('Ngày quét vượt ngày đã đóng theo chốt 15:00 UTC+7')
    frames = {s: f.loc[f.index <= asof].copy() for s, f in frames.items()}
    issues = issues[pd.to_datetime(issues.trading_date) <= asof].copy()
    snapshot_hash = training_fingerprint(frames, issues, asof)
    out = Path(args.out or ('report/oos_verified' if args.oos else 'report/tables'))
    out = out if out.is_absolute() else ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    existing_manifest = out / 'manifest.json'
    if existing_manifest.exists():
        previous = json.loads(existing_manifest.read_text(encoding='utf-8'))
        old_mode = previous.get('mode', 'in_sample')
        if old_mode != ('oos' if args.oos else 'in_sample'):
            raise ValueError('Thư mục --out đã chứa chế độ nghiên cứu khác; chọn thư mục riêng để không trộn bảng')
        if sorted(previous.get('universe',[]))!=sorted(symbols) or sorted(previous.get('excluded_symbols',[]))!=excluded:
            raise ValueError('Rổ/loại mã khác kết quả đã có; chọn thư mục --out riêng, không ghi đè nghiên cứu cũ')
    protocol = None
    if args.oos:
        protocol = locked_protocol(out, frames, issues, asof, args)
        family = protocol['primary_family']
        print(f"TRAIN: {protocol['train_start']} .. {protocol['train_end']}", flush=True)
        print(f"TEST: {protocol['test_start']} .. {asof.date()} | BY family={family}; B={args.resamples}", flush=True)
        print('Đang fit mức nền train và đánh giá holdout; không chọn lại ngưỡng...', flush=True)
        tables = oos_tables(frames, asof, issues, protocol, args.resamples, args.block_size)
        for name, frame in tables.items():
            if 'pattern_symbol' in name:
                frame = frame.reindex(columns=symbols, fill_value=0)
            save_csv(out, name, frame, index=name.startswith('q1_'))
        if args.sensitivity:
            cut = pd.Timestamp(protocol['train_end'])
            train = {s: f.loc[f.index <= cut] for s, f in frames.items()}
            counts, prob = sensitivity_tables(train, cut, issues)
            save_csv(out, 'train_sensitivity_counts.csv', counts)
            save_csv(out, 'train_sensitivity_q3.csv', prob)
    else:
        radar = build_radar(frames, asof, issues)
        years, tickers = q1_tables(radar.events)
        save_csv(out, 'q1_pattern_year.csv', years, True)
        save_csv(out, 'q1_pattern_symbol.csv', tickers.reindex(columns=symbols, fill_value=0), True)
        save_csv(out, 'signals.csv', radar.events)
        print('Đang tính Q2 trong mẫu, kỳ hạn 1/3/5/10/20 và phí 20/40 bps...', flush=True)
        q2, details, family = q2_tables(frames, radar.events, asof, issues,
                                       resamples=args.resamples, block_size=args.block_size,inference=False)
        save_csv(out, 'q2_summary.csv', q2)
        save_csv(out, 'q2_outcomes.csv', details)
        save_csv(out, 'execution_stress.csv', execution_stress(details))
        outcomes = build_setup_outcomes(frames, asof, issues)
        save_csv(out, 'q3_summary.csv', summarize_setups(outcomes))
        save_csv(out, 'q3_outcomes.csv', outcomes)
        if args.sensitivity:
            counts, prob = sensitivity_tables(frames, asof, issues)
            save_csv(out, 'sensitivity_counts.csv', counts)
            save_csv(out, 'sensitivity_q3.csv', prob)
    tables_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.csv')}
    manifest = dict(status='complete', mode='oos' if args.oos else 'in_sample', asof=str(asof.date()),
        study_role='robustness_exclusion' if excluded else 'main',full_universe=full_universe,excluded_symbols=excluded,
        generated_at=now.isoformat(), universe=symbols, horizons=HORIZONS, fees_bps=FEES,
        thresholds=asdict(Thresholds()), resamples=args.resamples, block_size=args.block_size, seed=2026,
        planned_directional_family=family, min_bootstrap_p=1/(args.resamples+1) if args.oos else None,
        inference_families={'q2_primary':family,'q3_secondary_scores':6} if args.oos else {},
        by_rank1_resolution_floor=family*sum(1/i for i in range(1,family+1))/(args.resamples+1),
        q_family='Q2 primary: 14 directed patterns x 5 horizons x 2 costs x 2 baselines',
        aggregation='long/MAE/hit per label; hypothesis contrasts equal-weighted per signal date',
        db_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), input_snapshot_sha256=snapshot_hash,
        source_hashes=source_hashes(), table_hashes=tables_hashes,
        python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
        limitations=['retrospective split; prior full-sample inspection' if args.oos else 'exploratory in-sample',
            'calendar inferred; index membership not point-in-time',
            'current price vintage; historical adjustments can revise past inputs',
            'block-bootstrap stationarity and block length assumptions; at least 10 calendar blocks required in each sample',
            'execution/slippage scenarios descriptive; actual fills cannot be established from daily OHLC',
            'Q4 not implemented'])
    if protocol is not None:
        manifest['protocol'] = protocol
        manifest['protocol_sha256'] = hashlib.sha256((out / 'oos_protocol.json').read_bytes()).hexdigest()
    temp = out / 'manifest.json.tmp'
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(out / 'manifest.json')
    print('Hoàn tất:', out)
    return 0


if __name__ == '__main__':
    # CLI tiếng Việt dùng UTF-8 cả khi stdout/stderr bị chuyển vào pipe trên Windows.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    raise SystemExit(main())
