"""Mô tả hình dạng nến Nhật từ dữ liệu OHLC (lớp tài chính thuần: không đọc/ghi, không gọi API).

Đầu vào: DataFrame có các cột open, high, low, close, **sắp xếp tăng dần theo thời gian**
(API SSI trả mới nhất trước nên phải sắp xếp trước khi gọi).

Nguyên tắc chống nhìn trước tương lai: mọi đại lượng tại dòng t chỉ dùng dữ liệu từ dòng t trở về trước.
Các đại lượng "tương đối" (thân dài/ngắn, Doji) so với trung bình của `avg_window` nến TRƯỚC đó.

Quy ước màu theo slide S7: Open < Close là nến tăng (white), Open > Close là nến giảm (black).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

OHLC = ("open", "high", "low", "close")


@dataclass(frozen=True)
class Thresholds:
    """Ngưỡng nhận diện. Giá trị mặc định theo quy ước phổ biến (cách đặt tham số kiểu TA-Lib),
    KHÔNG phải ngưỡng đã tối ưu: độ nhạy sẽ được khảo sát ở lớp analytics.
    """

    avg_window: int = 10          # số nến trước dùng để tính thân/biên độ trung bình
    doji_k: float = 0.10          # Doji: thân <= 10% biên độ trung bình
    long_k: float = 1.0           # thân dài: >= 1,0 x thân trung bình
    short_k: float = 1.0          # thân ngắn: <= 1,0 x thân trung bình
    shadow_tiny: float = 0.10     # bóng "rất ngắn": <= 10% biên độ của chính nến
    shadow_long_mult: float = 2.0  # Hammer/Shooting star: bóng dài >= 2 x thân
    long_shadow_pct: float = 0.60  # Doji chuồn chuồn/bia mộ: bóng dài >= 60% biên độ
    legged_pct: float = 0.30       # Doji chân dài: mỗi bóng >= 30% biên độ
    marubozu_shadow: float = 0.05  # Marubozu: mỗi bóng <= 5% biên độ
    trend_window: int = 10         # cửa sổ đo xu hướng trước mẫu hình
    trend_t: float = 1.0           # có xu hướng khi |thống kê t của lợi suất trung bình| >= 1
    strict_gap: bool = False       # True: Piercing/Dark Cloud phải mở cửa vượt đáy/đỉnh nến trước
    limit_pct: float = 0.07        # biên độ giá: HOSE 7%, HNX 10%, UPCOM 15%
    limit_tol: float = 0.005       # sai số làm tròn bước giá khi xác định "gần trần/sàn"

    def __post_init__(self):
        if self.avg_window < 2 or self.trend_window < 3:
            raise ValueError("avg_window phải >= 2 và trend_window phải >= 3")


def validate_ohlc(df: pd.DataFrame) -> None:
    """Báo lỗi rõ ràng nếu dữ liệu không dùng được (thay vì cho ra kết quả sai âm thầm)."""
    missing = [c for c in OHLC if c not in df.columns]
    if missing:
        raise ValueError(f"Thiếu cột: {', '.join(missing)}")
    if not df.index.is_monotonic_increasing:
        raise ValueError("Dữ liệu phải sắp xếp tăng dần theo thời gian (API trả mới nhất trước)")
    if df.index.has_duplicates:
        raise ValueError("Chỉ số thời gian bị trùng")
    px = df[list(OHLC)]
    if px.isna().any().any():
        raise ValueError("Có giá trị thiếu (NaN) trong OHLC")
    if (px <= 0).any().any():
        raise ValueError("Có giá không dương trong OHLC")
    top = df[["open", "close"]].max(axis=1)
    bottom = df[["open", "close"]].min(axis=1)
    bad = (df["high"] < top) | (df["low"] > bottom)
    if bad.any():
        raise ValueError(f"{int(bad.sum())} nến không hợp lệ: high < max(open, close) hoặc low > min(open, close)")


def describe_candles(
    df: pd.DataFrame,
    th: Thresholds | None = None,
    ref: pd.Series | None = None,
) -> pd.DataFrame:
    """Tính các đại lượng mô tả từng nến. Không sửa DataFrame đầu vào.

    ref: giá tham chiếu từng phiên (cùng chỉ số với df) để tính gap và cờ trần/sàn.
         Mặc định dùng giá đóng cửa hôm trước (lệch ở ngày giao dịch không hưởng quyền).
    """
    th = th or Thresholds()
    validate_ohlc(df)
    o, h, l, c = (df[k].astype(float) for k in OHLC)

    body_top = o.where(o >= c, c)
    body_bot = o.where(o <= c, c)
    body = body_top - body_bot
    rng = h - l
    upper = h - body_top
    lower = body_bot - l
    pos = rng > 0                 # phiên khóa trần/sàn (O=H=L=C) có biên độ 0: không phải nến hình dạng
    safe_rng = rng.where(pos)     # NaN khi biên độ bằng 0

    # Trung bình của các nến TRƯỚC (shift 1) để không dùng thông tin của chính nến đang xét.
    body_avg = body.rolling(th.avg_window).mean().shift(1)
    range_avg = rng.rolling(th.avg_window).mean().shift(1)

    doji = pos & (body <= th.doji_k * range_avg)
    long_body = pos & (body > 0) & (body >= th.long_k * body_avg)
    short_body = pos & (body <= th.short_k * body_avg)

    # Xu hướng: thống kê t của lợi suất log trung bình trong cửa sổ kết thúc tại t.
    logret = np.log(c / c.shift(1))
    w = th.trend_window
    trend_t = logret.rolling(w).mean() / logret.rolling(w).std() * np.sqrt(w)

    ref_s = c.shift(1) if ref is None else ref.reindex(df.index).astype(float)
    lim = th.limit_pct - th.limit_tol

    out = pd.DataFrame(
        {
            "open": o, "high": h, "low": l, "close": c,
            "body": body, "rng": rng, "upper": upper, "lower": lower,
            "body_top": body_top, "body_bot": body_bot,
            "white": c > o, "black": c < o,
            "body_pct": body / safe_rng,
            "upper_pct": upper / safe_rng,
            "lower_pct": lower / safe_rng,
            "body_avg": body_avg, "range_avg": range_avg,
            "doji": doji, "long_body": long_body, "short_body": short_body,
            "trend_t": trend_t,
            "ref": ref_s,
            "gap": o / ref_s - 1,
            "ret_ref": c / ref_s - 1,
            "limit_up": (c / ref_s - 1) >= lim,      # NaN (thiếu tham chiếu) cho kết quả False
            "limit_down": (c / ref_s - 1) <= -lim,
        },
        index=df.index,
    )
    return out
