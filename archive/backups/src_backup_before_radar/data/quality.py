"""Kiểm tra chất lượng dữ liệu nến: phát hiện vấn đề, loại dòng hỏng, loại nến chưa đóng.

Quy ước dữ liệu vào: DataFrame của MỘT mã, chỉ số là ngày (DatetimeIndex), các cột lowercase
open/high/low/close/volume (tùy chọn: ref = giá tham chiếu, value).
Mọi hàm kiểm tra trả về bảng vấn đề với cột: symbol, trading_date, check, severity, detail.
severity: 'error' (loại dòng khỏi dữ liệu lưu), 'warning' (giữ lại nhưng ghi nhận), 'info'.
Lớp này không phụ thuộc finance (finance đứng sau data trong chuỗi phụ thuộc).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

VN = timezone(timedelta(hours=7))
ISSUE_COLS = ["symbol", "trading_date", "check", "severity", "detail"]


def _frame(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=ISSUE_COLS)


def _d(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def empty_issues() -> pd.DataFrame:
    return _frame([])


def ex_event_mask(df: pd.DataFrame, rel_tol: float = 1e-6) -> pd.Series:
    """True ở phiên mà giá tham chiếu khác giá đóng cửa phiên liền trước.

    Dấu hiệu của ngày giao dịch không hưởng quyền (tham chiếu bị điều chỉnh) hoặc thiếu phiên liền trước.
    Cần cột 'ref'; không có thì trả về toàn False. Mẫu hình nến đi qua ngày này nên được loại khi kiểm định.
    """
    if "ref" not in df.columns:
        return pd.Series(False, index=df.index)
    prev = df["close"].shift(1)
    return ((df["ref"] - prev).abs() > rel_tol * prev.abs()).fillna(False)


def check_ohlc(df: pd.DataFrame, symbol: str = "", limit_pct: float = 0.07, limit_tol: float = 0.005,
               max_gap_days: int = 10) -> pd.DataFrame:
    """Các kiểm tra trên một mã: trùng ngày, giá không hợp lệ, high/low sai, khối lượng, vượt biên độ,
    ngày đi quyền, khoảng trống thời gian dài."""
    rows = []
    add = lambda d, check, sev, detail: rows.append((symbol, _d(d), check, sev, detail))

    for d in df.index[df.index.duplicated(keep=False)].unique():
        add(d, "duplicate_date", "warning", "trùng ngày (giữ dòng cuối)")

    s = df[~df.index.duplicated(keep="last")].sort_index()
    px = s[["open", "high", "low", "close"]]
    bad_px = px.isna().any(axis=1) | (px <= 0).any(axis=1)
    for d in s.index[bad_px]:
        add(d, "non_positive_price", "error", "giá thiếu hoặc không dương")

    top = s[["open", "close"]].max(axis=1)
    bottom = s[["open", "close"]].min(axis=1)
    inconsistent = ~bad_px & ((s["high"] < top) | (s["low"] > bottom))
    for d in s.index[inconsistent]:
        add(d, "inconsistent_ohlc", "error", "high < max(open, close) hoặc low > min(open, close)")

    vol = s["volume"] if "volume" in s.columns else pd.Series(np.nan, index=s.index)
    for d in s.index[vol < 0]:
        add(d, "negative_volume", "error", "khối lượng âm")
    for d in s.index[vol.isna()]:
        add(d, "missing_volume", "warning", "thiếu khối lượng")
    for d in s.index[(vol == 0) & (s["high"] > s["low"])]:
        add(d, "zero_volume", "warning", "khối lượng 0 nhưng giá có biên độ")

    ref = s["ref"] if "ref" in s.columns else s["close"].shift(1)
    ret = s["close"] / ref - 1
    for d in s.index[(ret.abs() > limit_pct + limit_tol).fillna(False)]:
        add(d, "limit_exceeded", "warning", f"{ret[d]:+.1%} so với tham chiếu, vượt biên độ {limit_pct:.0%}")

    for d in s.index[ex_event_mask(s)]:
        add(d, "ex_event", "info", "tham chiếu khác đóng cửa hôm trước: ngày không hưởng quyền hoặc thiếu phiên liền trước")

    gaps = s.index.to_series().diff().dt.days
    for d in gaps.index[(gaps > max_gap_days).fillna(False)]:
        add(d, "long_gap", "warning", f"cách phiên trước {int(gaps[d])} ngày")
    return _frame(rows)


def check_cross(ohlc: pd.DataFrame, summary: pd.DataFrame, symbol: str = "", rel_tol: float = 1e-9) -> pd.DataFrame:
    """Đối chiếu chéo hai nguồn: nến (ohlc) với tổng hợp giao dịch (securitiesSummary).
    Không biết nguồn nào đúng nên chỉ ghi 'warning'."""
    rows = []
    add = lambda d, check, detail: rows.append((symbol, _d(d), check, "warning", detail))
    o = ohlc[~ohlc.index.duplicated(keep="last")]
    s = summary[~summary.index.duplicated(keep="last")]

    for d in o.index.difference(s.index):
        add(d, "missing_in_summary", "có trong ohlc nhưng thiếu trong securitiesSummary")
    for d in s.index.difference(o.index):
        add(d, "missing_in_ohlc", "có trong securitiesSummary nhưng thiếu trong ohlc")

    both = o.index.intersection(s.index)
    pairs = [(c, c) for c in ("open", "high", "low", "close")] + [("volume", "total_match")]
    for oc, sc in pairs:
        if oc not in o.columns or sc not in s.columns:
            continue
        a, b = o.loc[both, oc], s.loc[both, sc]
        mism = (a - b).abs() > rel_tol * a.abs().clip(lower=1)
        for d in both[mism.fillna(False).to_numpy()]:
            add(d, f"cross_mismatch_{oc}", f"ohlc={a[d]:g} khác securitiesSummary={b[d]:g}")
    return _frame(rows)


def check_calendar(frames: dict, min_share: float = 0.5, min_symbols: int = 3) -> pd.DataFrame:
    """Phát hiện phiên thiếu theo lịch chung: phiên có ở ít nhất min_share số mã được coi là phiên giao dịch
    của thị trường; mã nào thiếu phiên đó (trong khoảng ngày của chính mã) thì ghi nhận.
    Cần ít nhất min_symbols mã mới có ý nghĩa."""
    if len(frames) < min_symbols:
        return empty_issues()
    counts = pd.concat([pd.Series(1, index=f.index.unique()) for f in frames.values()]).groupby(level=0).sum()
    market_days = counts[counts >= max(1, math.ceil(min_share * len(frames)))].index
    rows = []
    for sym, f in frames.items():
        if f.empty:
            continue
        span = market_days[(market_days >= f.index.min()) & (market_days <= f.index.max())]
        for d in span.difference(f.index):
            rows.append((sym, _d(d), "missing_session", "warning", "phiên có ở phần lớn các mã nhưng thiếu ở mã này"))
    return _frame(rows)


def check_freshness(last, today=None, symbol: str = "", max_stale_days: int = 5) -> pd.DataFrame:
    """Cảnh báo dữ liệu cũ: ngày cuối cùng cách hôm nay quá max_stale_days ngày lịch."""
    today = pd.Timestamp(today or datetime.now(VN).date())
    if last is None:
        return _frame([(symbol, _d(today), "no_data", "error", "chưa có dữ liệu")])
    days = (today - pd.Timestamp(last)).days
    if days > max_stale_days:
        return _frame([(symbol, _d(last), "stale_data", "warning", f"dữ liệu cũ {days} ngày")])
    return empty_issues()


def split_valid(df: pd.DataFrame, issues: pd.DataFrame):
    """Tách (dòng hợp lệ, dòng bị loại). Dòng bị loại là các ngày có vấn đề mức 'error'.
    Trùng ngày được gộp bằng cách giữ dòng cuối. Kết quả hợp lệ đã sắp xếp tăng dần."""
    err_dates = pd.to_datetime(issues.loc[issues["severity"] == "error", "trading_date"])
    drop = df.index.isin(err_dates)
    clean = df[~drop]
    clean = clean[~clean.index.duplicated(keep="last")].sort_index()
    return clean, df[drop]


def drop_open_candle(df: pd.DataFrame, now: datetime | None = None, close_hour: int = 15):
    """Bỏ nến của ngày hôm nay nếu phiên chưa kết thúc (trước close_hour giờ Việt Nam).
    ATC kết thúc 14:45, lấy 15:00 để chừa độ trễ dữ liệu. Trả về (df, số dòng đã bỏ)."""
    now = now or datetime.now(VN)
    now = now.astimezone(VN) if now.tzinfo else now.replace(tzinfo=VN)
    if now.hour >= close_hour:
        return df, 0
    mask = pd.DatetimeIndex(df.index).normalize() == pd.Timestamp(now.date())
    return df[~mask], int(mask.sum())
