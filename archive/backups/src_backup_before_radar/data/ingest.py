"""Thu thập dữ liệu: gọi SSI API, làm sạch và kiểm tra, ghi vào SQLite.

Chạy:
    python -m data.ingest --symbols FPT,VCB --since 2023-01-01
    python -m data.ingest                      # lấy danh sách từ universe_vn30.txt, 5 năm gần nhất
    python -m data.ingest --status             # xem trạng thái dữ liệu
    python -m data.ingest --audit              # kiểm tra chất lượng toàn bộ CSDL
    python -m data.ingest --audit --check ex_event   # liệt kê các ngày nghi không hưởng quyền
    python -m data.ingest --ref-report FPT,ECO       # chẩn đoán giá tham chiếu và điều chỉnh giá
    python -m data.ingest --log                      # 20 lần nạp gần nhất
    python -m data.ingest --issues --symbols ECO     # truy vết dòng bị loại và các cảnh báo đã ghi
    python -m data.ingest --symbols FPT --full-refresh   # xóa và nạp lại từ đầu

Cập nhật tăng dần: lần sau chỉ lấy từ (ngày cuối đã lưu - overlap_days). SSI trả giá đã điều chỉnh ngược về
hiện tại (xem docs/api_notes.md) nên phần chồng lấn dùng để phát hiện ngày đi quyền mới: khi giá đã lưu bị đổi,
tự động nạp lại toàn bộ lịch sử của mã đó (tắt bằng auto_refresh=False).
Lỗi của một mã không làm dừng các mã khác; mọi lần nạp đều ghi vào bảng ingest_log.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from data import db, quality
from ssi_api.client import to_date

log = logging.getLogger(__name__)
UNIVERSE_FILE = Path(__file__).with_name("universe_vn30.txt")


# ---------------------------------------------------------------- chuẩn hóa dữ liệu thô từ API
def to_snake(name: str) -> str:
    """camelCase của API -> snake_case của CSDL (totalMatchValue -> total_match_value)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _empty(cols) -> pd.DataFrame:
    return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="trading_date"), dtype=float)


def _by_date(raw: pd.DataFrame, cols) -> pd.DataFrame:
    df = raw.rename(columns=to_snake)
    dates = to_date(df["trading_date"])
    if dates.isna().any():
        raise ValueError("Không đọc được ngày giao dịch từ API (định dạng có thể đã đổi)")
    df.index = pd.DatetimeIndex(dates, name="trading_date")
    return df.sort_index(kind="stable").reindex(columns=cols).astype(float)


def normalize_ohlc(raw: pd.DataFrame | None) -> pd.DataFrame:
    """Phản hồi ohlc -> chỉ số ngày, sắp xếp tăng dần, các cột db.OHLC_COLS dạng số."""
    return _empty(db.OHLC_COLS) if raw is None or raw.empty else _by_date(raw, db.OHLC_COLS)


def normalize_summary(raw: pd.DataFrame | None) -> pd.DataFrame:
    """Phản hồi securitiesSummary -> chỉ số ngày, tăng dần, các cột db.SUMMARY_COLS (thiếu thì NaN)."""
    return _empty(db.SUMMARY_COLS) if raw is None or raw.empty else _by_date(raw, db.SUMMARY_COLS)


def load_universe(path=None) -> list[str]:
    """Đọc danh sách mã từ tệp văn bản (bỏ dòng trống và phần sau dấu #)."""
    path = Path(path or UNIVERSE_FILE)
    symbols = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.split("#", 1)[0].strip().upper()
        if s:
            if not re.fullmatch(r"[A-Z0-9]{1,20}", s):
                raise ValueError(f"Mã không hợp lệ trong {path.name}: {s!r}")
            symbols.append(s)
    if not symbols:
        raise ValueError(
            f"Chưa có mã nào. Dùng --symbols FPT,VCB hoặc điền danh sách vào {path} (xem hướng dẫn trong tệp)."
        )
    return symbols


# ---------------------------------------------------------------- nạp một mã
def _count_revised(conn, symbol: str, new: pd.DataFrame) -> int:
    """Số phiên đã lưu mà dữ liệu mới trả về giá đóng cửa khác: dấu hiệu API điều chỉnh giá lùi về trước."""
    if new.empty:
        return 0
    stored = db.load_ohlc(conn, symbol, start=new.index.min(), end=new.index.max())
    common = stored.index.intersection(new.index)
    if common.empty:
        return 0
    a, b = stored.loc[common, "close"], new.loc[common, "close"]
    return int(((a - b).abs() > 1e-9 * a.abs()).sum())


def _concat(frames) -> pd.DataFrame:
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else quality.empty_issues()


def ingest_symbol(client, conn, symbol: str, since, today=None, now: datetime | None = None,
                  overlap_days: int = 10, full_refresh: bool = False, page_size: int = 1000,
                  limit_pct: float = 0.07, auto_refresh: bool = True, note: str = "") -> dict:
    """Nạp một mã. Không ném lỗi của riêng mã đó: trả về dict có status 'ok' hoặc 'failed'.

    SSI trả giá đã điều chỉnh ngược về hiện tại, nên mỗi ngày đi quyền mới làm đổi thang của TOÀN BỘ lịch sử.
    Khi phát hiện phiên đã lưu bị đổi giá (auto_refresh=True) hàm tự nạp lại toàn bộ lịch sử của mã đó để
    CSDL không bị lẫn hai thang giá. limit_pct: biên độ giá của sàn (HOSE 0,07; HNX 0,10; UPCOM 0,15).
    """
    now = now or datetime.now(db.VN)
    today = pd.Timestamp(today or now.date())
    last = None if full_refresh else db.last_date(conn, symbol)
    start = pd.Timestamp(since) if last is None else max(pd.Timestamp(since), last - timedelta(days=overlap_days))
    res = {"symbol": symbol, "status": "ok", "n_ohlc": 0, "n_summary": 0, "n_open_dropped": 0,
           "n_errors": 0, "n_warnings": 0, "message": "", "issues": quality.empty_issues()}
    try:
        ohlc = normalize_ohlc(client.ohlc(symbol, start, today, page_size=page_size))
        summ = normalize_summary(client.securities_summary(symbol, start, today, page_size=page_size))
        ohlc, res["n_open_dropped"] = quality.drop_open_candle(ohlc, now)
        summ, _ = quality.drop_open_candle(summ, now)
        summ = summ[~summ.index.duplicated(keep="last")]

        issues = _concat([quality.check_ohlc(ohlc, symbol, limit_pct=limit_pct),
                          quality.check_cross(ohlc, summ, symbol)])
        clean, rejected = quality.split_valid(ohlc, issues)
        summ = summ[~summ.index.isin(rejected.index)]

        revised = 0 if full_refresh else _count_revised(conn, symbol, clean)
        if revised and auto_refresh:
            log.warning("%s: %d phiên đã lưu bị API đổi giá (điều chỉnh quyền), nạp lại toàn bộ", symbol, revised)
            return ingest_symbol(client, conn, symbol, since, today=today, now=now, overlap_days=overlap_days,
                                 full_refresh=True, page_size=page_size, limit_pct=limit_pct, auto_refresh=False,
                                 note=f"[tự nạp lại toàn bộ vì {revised} phiên đã lưu bị API điều chỉnh giá] ")
        if revised:
            extra = pd.DataFrame([(symbol, _iso(clean.index.max()), "revised_history", "warning",
                                   f"{revised} phiên đã lưu bị API trả giá khác: nghi điều chỉnh giá lùi về trước, nên chạy --full-refresh")],
                                 columns=quality.ISSUE_COLS)
            issues = _concat([issues, extra])

        with db.session(conn):
            if full_refresh:
                db.delete_symbol(conn, symbol, commit=False)
            else:
                db.delete_issues(conn, symbol, from_date=start, commit=False)   # kết quả kiểm tra mới thay cho cũ
            res["n_ohlc"] = db.upsert_ohlc(conn, symbol, clean, commit=False)
            res["n_summary"] = db.upsert_summary(conn, symbol, summ, commit=False)
            db.log_issues(conn, issues, now=now, commit=False)
        res["issues"] = issues
        res["n_errors"] = int((issues["severity"] == "error").sum())
        res["n_warnings"] = int((issues["severity"] == "warning").sum())
        counts = issues.groupby("check").size().to_dict()
        res["message"] = note + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    except Exception as e:  # noqa: BLE001 - lỗi một mã không được làm dừng cả đợt nạp
        log.exception("Nạp %s thất bại", symbol)
        res["status"], res["message"] = "failed", (note + f"{type(e).__name__}: {e}")[:500]

    db.log_ingest(conn, symbol, res["status"], d_from=start, d_to=today, n_ohlc=res["n_ohlc"],
                  n_summary=res["n_summary"], n_open_dropped=res["n_open_dropped"],
                  n_errors=res["n_errors"], n_warnings=res["n_warnings"], message=res["message"], now=now)
    return res


def _iso(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def ingest_many(client, conn, symbols, since, **kwargs) -> pd.DataFrame:
    """Nạp lần lượt nhiều mã; trả về bảng tóm tắt (một dòng mỗi mã)."""
    results = [ingest_symbol(client, conn, s, since, **kwargs) for s in symbols]
    cols = ["symbol", "status", "n_ohlc", "n_summary", "n_open_dropped", "n_errors", "n_warnings", "message"]
    return pd.DataFrame([{k: r[k] for k in cols} for r in results], columns=cols)


def audit_db(conn, today=None) -> pd.DataFrame:
    """Kiểm tra chất lượng toàn bộ dữ liệu đã lưu: từng mã, phiên thiếu theo lịch chung, dữ liệu cũ."""
    frames = {s: db.load_ohlc(conn, s) for s in db.list_symbols(conn)}
    parts = []
    for s, f in frames.items():
        parts.append(quality.check_ohlc(f, s))
        parts.append(quality.check_freshness(f.index.max(), today, s))
    parts.append(quality.check_calendar(frames))
    return _concat(parts)


def ref_report(conn, symbol: str, jump_pct: float = 7.5, min_move_pct: float = 1.0) -> pd.DataFrame:
    """Chẩn đoán giả thuyết 'giá tham chiếu = close - priceChange' và việc giá có được điều chỉnh hay không.

    Cột trả về (mỗi phiên): close, prev_close, delta_close, ret_close_pct (lợi suất theo close, %),
    price_change, price_change_percentage, ref_implied = close - price_change,
    ratio_change = price_change / delta_close (chỉ tính ở phiên giá biến động >= min_move_pct %),
    ref_mismatch (ref_implied khác prev_close), pct_diff (ret_close_pct - price_change_percentage).
    Ý nghĩa: nếu priceChange được điều chỉnh lùi về trước còn close là giá thô thì ratio_change sẽ gần
    một hằng số khác 1 giữa hai ngày đi quyền (và bằng hệ số điều chỉnh của sự kiện).
    """
    o, s = db.load_ohlc(conn, symbol)[["close"]], db.load_summary(conn, symbol)
    d = o.join(s[["price_change", "price_change_percentage"]])
    d["prev_close"] = d["close"].shift(1)
    d["delta_close"] = d["close"] - d["prev_close"]
    d["ret_close_pct"] = (d["close"] / d["prev_close"] - 1) * 100
    d["ref_implied"] = d["close"] - d["price_change"]
    big = d["ret_close_pct"].abs() >= min_move_pct
    d["ratio_change"] = (d["price_change"] / d["delta_close"]).where(big)
    d["ref_mismatch"] = ((d["ref_implied"] - d["prev_close"]).abs() > 1e-6 * d["prev_close"].abs()).fillna(False)
    d["pct_diff"] = d["ret_close_pct"] - d["price_change_percentage"]
    return d[["close", "prev_close", "delta_close", "ret_close_pct", "price_change", "price_change_percentage",
              "ref_implied", "ratio_change", "ref_mismatch", "pct_diff"]]


def print_ref_report(d: pd.DataFrame, symbol: str, jump_pct: float = 7.5) -> None:
    """In bản tóm tắt ngắn của ref_report (đủ để gửi kèm khi cần hỏi)."""
    n = len(d)
    print(f"\n=== {symbol}: {n} phiên ===")
    if n == 0:
        return
    by_year = d["ref_mismatch"].groupby(d.index.year).agg(["sum", "count"])
    print("Phiên có (close - priceChange) khác đóng cửa hôm trước, theo năm:",
          ", ".join(f"{y}: {int(r['sum'])}/{int(r['count'])}" for y, r in by_year.iterrows()))
    bad_pct = (d["pct_diff"].abs() > 0.05).sum()
    print(f"Phiên mà lợi suất theo close lệch priceChangePercentage > 0,05 điểm %: {int(bad_pct)}")
    jumps = d[d["ret_close_pct"].abs() > jump_pct]
    print(f"Phiên close biến động > {jump_pct}% so với đóng cửa hôm trước (vượt biên độ HOSE nên nghi ngày đi quyền): {len(jumps)}")
    if len(jumps):
        print(jumps[["prev_close", "close", "ret_close_pct", "price_change_percentage"]].head(10).round(2).to_string())
    q = d["ratio_change"].groupby(d.index.to_period("Q")).agg(["median", "count"])
    q = q[q["count"] > 0]
    if len(q):
        print("priceChange / (close - đóng cửa hôm trước), trung vị theo quý (≈1 nếu priceChange cùng thang với close):")
        print(q.round(4).to_string())
    print("Vài dòng mẫu (3 phiên đầu, 3 phiên cuối):")
    print(pd.concat([d.head(3), d.tail(3)])[["prev_close", "close", "price_change", "price_change_percentage",
                                           "ref_implied", "ratio_change"]].round(4).to_string())


def print_audit(issues: pd.DataFrame, check: str | None = None, limit: int = 30) -> None:
    """In kết quả kiểm tra: tổng số, đếm theo loại, rồi liệt kê chi tiết (một loại cụ thể hoặc các lỗi/cảnh báo)."""
    print(f"{len(issues)} vấn đề")
    if issues.empty:
        return
    print(issues.groupby(["check", "severity"]).size().to_string())
    shown = issues[issues["check"] == check] if check else issues[issues["severity"] != "info"]
    if not shown.empty:
        print(f"\nChi tiết ({'loại ' + check if check else 'lỗi và cảnh báo'}), tối đa {limit} dòng:")
        print(shown.sort_values(["symbol", "trading_date"]).head(limit).to_string(index=False))


# ---------------------------------------------------------------- dòng lệnh
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m data.ingest", description="Nạp dữ liệu SSI vào SQLite")
    ap.add_argument("--symbols", help="Danh sách mã cách nhau bằng dấu phẩy, ví dụ FPT,VCB")
    ap.add_argument("--symbols-file", help=f"Tệp danh sách mã (mặc định {UNIVERSE_FILE.name})")
    ap.add_argument("--since", help="Ngày bắt đầu YYYY-MM-DD (mặc định 5 năm trước)")
    ap.add_argument("--db", help="Đường dẫn SQLite (mặc định RADAR_DB_PATH hoặc storage/radar.db)")
    ap.add_argument("--full-refresh", action="store_true", help="Xóa dữ liệu của mã rồi nạp lại từ đầu")
    ap.add_argument("--status", action="store_true", help="Chỉ in trạng thái dữ liệu")
    ap.add_argument("--audit", action="store_true", help="Chỉ kiểm tra chất lượng dữ liệu đã lưu")
    ap.add_argument("--check", help="Với --audit: liệt kê chi tiết một loại vấn đề, ví dụ ex_event")
    ap.add_argument("--log", action="store_true", help="In 20 lần nạp gần nhất")
    ap.add_argument("--issues", action="store_true",
                    help="In các vấn đề chất lượng đã ghi (lọc bằng --symbols, --check); dùng để truy vết dòng bị loại")
    ap.add_argument("--limit-pct", type=float, default=0.07, help="Biên độ giá của sàn (HOSE 0.07, HNX 0.10, UPCOM 0.15)")
    ap.add_argument("--ref-report", metavar="MÃ", help="Chẩn đoán giá tham chiếu/điều chỉnh giá của các mã (cách nhau bằng dấu phẩy)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="  [%(levelname)s] %(message)s")

    conn = db.connect(args.db)
    if args.status:
        print(db.data_status(conn).to_string(index=False))
        return 0
    if args.log:
        cols = ["run_at", "symbol", "status", "n_ohlc", "n_errors", "n_warnings", "message"]
        print(db.read_log(conn, 20)[cols].to_string(index=False))
        return 0
    if args.issues:
        syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else None
        print_audit(db.read_issues(conn, symbols=syms, check=args.check), args.check)
        return 0
    if args.audit:
        print_audit(audit_db(conn), args.check)
        return 0
    if args.ref_report:
        for sym in [s.strip().upper() for s in args.ref_report.split(",") if s.strip()]:
            print_ref_report(ref_report(conn, sym), sym)
        return 0

    symbols = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
               if args.symbols else load_universe(args.symbols_file))
    since = pd.Timestamp(args.since) if args.since else pd.Timestamp(date.today() - timedelta(days=5 * 365 + 1))

    from ssi_api.client import SSIClient  # nhập muộn: các lệnh --status/--audit không cần khóa API
    result = ingest_many(SSIClient(), conn, symbols, since, full_refresh=args.full_refresh,
                         limit_pct=args.limit_pct)
    print(result.to_string(index=False))
    return 1 if (result["status"] != "ok").any() else 0


if __name__ == "__main__":
    sys.exit(main())
