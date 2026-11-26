"""Tạo bảng radar từ nến đã lưu. Hàm thuần, không I/O và không ước lượng hiệu quả đầu tư."""
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from finance.candles import Thresholds
from finance.patterns import detect_patterns, detect_setups, pattern_catalog

EVENT_COLS = ["symbol", "date", "name", "name_vi", "bias", "kind", "confirmation"]
LATEST_COLS = ["symbol", "data_date", "close", "change_pct", "volume", "patterns", "setups", "status"]


@dataclass
class RadarResult:
    latest: pd.DataFrame
    events: pd.DataFrame
    missing_sessions: pd.DataFrame
    market_days: pd.DatetimeIndex


def infer_market_days(frames) -> pd.DatetimeIndex:
    """Lịch ước lượng từ ngày xuất hiện ở ít nhất một nửa số mã có dữ liệu.

    Đây không phải lịch chính thức. Một ngày thiếu ở toàn bộ nhóm mã không thể được phát hiện.
    """
    available = [frame for frame in frames.values() if not frame.empty]
    if not available:
        return pd.DatetimeIndex([])
    counts = pd.concat([pd.Series(1, index=frame.index.unique()) for frame in available]).groupby(level=0).sum()
    return pd.DatetimeIndex(counts[counts >= max(1, math.ceil(len(available) / 2))].index).sort_values()


def _valid_rows(frame):
    px = frame[["open", "high", "low", "close"]].astype(float)
    valid = (
        np.isfinite(px).all(axis=1) & (px > 0).all(axis=1)
        & (px["high"] >= px[["open", "close"]].max(axis=1))
        & (px["low"] <= px[["open", "close"]].min(axis=1))
    )
    if 'volume' in frame:
        volume=frame.volume.astype(float)
        valid &= volume.isna() | (np.isfinite(volume)&volume.ge(0))
    return valid


def build_radar(frames, asof, issues=None, th=None, market_days=None) -> RadarResult:
    th = th or Thresholds()
    asof = pd.Timestamp(asof).normalize()
    # Cắt trước khi suy lịch và nhận diện để không dùng ngày sau thời điểm đang xem.
    frames = {symbol: frame.loc[frame.index <= asof].copy() for symbol, frame in frames.items()}
    market_days = (infer_market_days(frames) if market_days is None else
                   pd.DatetimeIndex(market_days).drop_duplicates().sort_values())
    market_days = market_days[market_days <= asof]
    catalog = pattern_catalog().set_index("name")
    event_rows, latest_rows, missing_rows = [], [], []
    for symbol, frame in frames.items():
        if frame.empty:
            latest_rows.append([symbol, pd.NaT, np.nan, np.nan, np.nan, "", "", "Chưa có dữ liệu"])
            continue
        original_last = frame.index.max()
        valid = _valid_rows(frame)
        if issues is not None and not issues.empty:
            rejected_dates = pd.to_datetime(issues.loc[
                (issues["symbol"] == symbol) & (issues["severity"] == "error"), "trading_date"
            ])
            valid &= ~frame.index.isin(rejected_dates)
        clean = frame.loc[valid]
        span = market_days[(market_days >= frame.index.min()) & (market_days <= original_last)]
        for day in span.difference(frame.index):
            missing_rows.append((symbol, day, "Thiếu so với lịch ước lượng từ các mã trong rổ"))
        present = pd.Series(False, index=market_days)
        present.loc[present.index.intersection(clean.index)] = True
        eligible = {}
        for candles in (1, 2, 3):
            # trend_window lợi suất cần trend_window + 1 giá trước mẫu hình.
            width = max(th.avg_window, th.trend_window + 1) + candles
            eligible[candles] = present.rolling(width, min_periods=width).sum().eq(width)
        current_patterns, current_setups = [], []
        if not clean.empty:
            for kind, signals in (("pattern", detect_patterns(clean, th)), ("setup", detect_setups(clean, th))):
                for name in signals.columns:
                    info = catalog.loc[name]
                    mask = eligible[int(info["candles"])].reindex(signals.index, fill_value=False)
                    dates = signals.index[signals[name] & mask]
                    for day in dates:
                        confirmation = ""
                        if kind == "setup":
                            position = clean.index.get_loc(day)
                            first = clean.iloc[position - 1]
                            midpoint = (first["open"] + first["close"]) / 2
                            if info["bias"] == "bullish":
                                confirmation = f"Phiên kế tiếp: nến tăng và đóng cửa > {midpoint:,.2f}"
                            else:
                                confirmation = f"Phiên kế tiếp: nến giảm và đóng cửa < {midpoint:,.2f}"
                        event_rows.append((symbol, day, name, info["name_vi"], info["bias"], kind, confirmation))
                        if day == asof:
                            (current_patterns if kind == "pattern" else current_setups).append(info["name_vi"])
        if original_last != asof:
            status = "Thiếu nến ngày đang xem"
        elif asof not in clean.index:
            status = "Nến bị lỗi chất lượng"
        elif asof not in eligible[1].index or not eligible[1].loc[asof]:
            status = "Chưa đủ cửa sổ liên tiếp"
        else:
            status = "Đã quét"
        row = frame.iloc[-1]
        change = np.nan
        if asof in market_days and asof in clean.index:
            pos = market_days.get_loc(asof)
            if pos > 0 and market_days[pos - 1] in clean.index:
                change = (clean.loc[asof, "close"] / clean.loc[market_days[pos - 1], "close"] - 1) * 100
        latest_rows.append((symbol, original_last, row["close"], change, row.get("volume", np.nan),
                            "; ".join(current_patterns), "; ".join(current_setups), status))
    events = pd.DataFrame(event_rows, columns=EVENT_COLS).sort_values(["date", "symbol", "name"]).reset_index(drop=True)
    latest = pd.DataFrame(latest_rows, columns=LATEST_COLS)
    missing = pd.DataFrame(missing_rows, columns=["symbol", "date", "detail"])
    return RadarResult(latest, events, missing, market_days)
