"""Nhận diện mẫu hình nến theo slide S7 (lớp tài chính thuần: nhận DataFrame, trả DataFrame).

Quy ước quan trọng:
- Tín hiệu gắn vào nến CUỐI của mẫu hình (ngày mẫu hình hoàn thành). Vì nến chỉ biết sau khi đóng cửa,
  tín hiệu chỉ dùng được từ phiên KẾ TIẾP: khi kiểm định phải tính lợi suất từ giá mở cửa t+1.
- Mẫu hình đảo chiều chỉ tính khi có xu hướng ngược phía trước (đo ở nến ngay trước mẫu hình).
- Các Doji con (chuồn chuồn, bia mộ, chân dài) cũng làm cột `doji` bằng True.
- Phiên khóa trần/sàn (O=H=L=C) có biên độ 0, không được tính là Doji hay bất kỳ mẫu hình nào.
- Có thể gán đồng thời nhiều mẫu hình cho cùng một ngày.
Chưa có: Abandoned Baby, Three White Soldiers (có trong slide) và yêu cầu gap của Shooting Star.
"""
from __future__ import annotations

import pandas as pd

from finance.candles import Thresholds, describe_candles

# name, tên tiếng Việt, hướng kỳ vọng, số nến, loại ("pattern" hoặc "setup" = mới có các nến đầu)
_CATALOG = [
    ("doji", "Doji", "neutral", 1, "pattern"),
    ("dragonfly_doji", "Doji chuồn chuồn", "neutral", 1, "pattern"),
    ("gravestone_doji", "Doji bia mộ", "neutral", 1, "pattern"),
    ("long_legged_doji", "Doji chân dài", "neutral", 1, "pattern"),
    ("marubozu_white", "Marubozu tăng", "bullish", 1, "pattern"),
    ("marubozu_black", "Marubozu giảm", "bearish", 1, "pattern"),
    ("spinning_top", "Con quay", "neutral", 1, "pattern"),
    ("hammer", "Búa (Hammer)", "bullish", 1, "pattern"),
    ("inverted_hammer", "Búa ngược", "bullish", 1, "pattern"),
    ("hanging_man", "Người treo cổ (Hanging man)", "bearish", 1, "pattern"),
    ("shooting_star", "Sao băng (Shooting star)", "bearish", 1, "pattern"),
    ("bullish_engulfing", "Bao trùm tăng", "bullish", 2, "pattern"),
    ("bearish_engulfing", "Bao trùm giảm", "bearish", 2, "pattern"),
    ("piercing", "Xuyên thấu (Piercing)", "bullish", 2, "pattern"),
    ("dark_cloud_cover", "Mây đen che phủ", "bearish", 2, "pattern"),
    ("bullish_harami", "Harami tăng", "bullish", 2, "pattern"),
    ("bearish_harami", "Harami giảm", "bearish", 2, "pattern"),
    ("morning_star", "Sao mai (Morning star)", "bullish", 3, "pattern"),
    ("evening_star", "Sao hôm (Evening star)", "bearish", 3, "pattern"),
    ("morning_star_setup", "Sắp có Sao mai (đã có 2 nến đầu)", "bullish", 2, "setup"),
    ("evening_star_setup", "Sắp có Sao hôm (đã có 2 nến đầu)", "bearish", 2, "setup"),
]


def pattern_catalog(kind: str | None = None) -> pd.DataFrame:
    """Danh mục mẫu hình: name, name_vi, bias, candles, kind. kind lọc 'pattern' hoặc 'setup'."""
    cat = pd.DataFrame(_CATALOG, columns=["name", "name_vi", "bias", "candles", "kind"])
    return cat if kind is None else cat[cat["kind"] == kind].reset_index(drop=True)


def _trend_flags(d: pd.DataFrame, th: Thresholds, n_candles: int):
    """Có xu hướng tăng/giảm tại nến ngay TRƯỚC nến đầu của mẫu hình (dịch n_candles dòng)."""
    up = (d["trend_t"] >= th.trend_t).shift(n_candles, fill_value=False)
    down = (d["trend_t"] <= -th.trend_t).shift(n_candles, fill_value=False)
    return up, down


def _star_setups(d: pd.DataFrame, th: Thresholds):
    """Hai nến đầu của Sao mai/Sao hôm: nến dài ngược xu hướng rồi nến thân ngắn có gap (theo thân nến)."""
    up2, down2 = _trend_flags(d, th, 2)
    top1, bot1 = d["body_top"].shift(1), d["body_bot"].shift(1)
    long1 = d["long_body"].shift(1, fill_value=False)
    white1 = d["white"].shift(1, fill_value=False)
    black1 = d["black"].shift(1, fill_value=False)
    morning = down2 & black1 & long1 & d["short_body"] & (d["body_top"] < bot1)
    evening = up2 & white1 & long1 & d["short_body"] & (d["body_bot"] > top1)
    return morning, evening


def detect_patterns(df: pd.DataFrame, th: Thresholds | None = None) -> pd.DataFrame:
    """Trả về DataFrame bool (cùng chỉ số với df), mỗi cột một mẫu hình trong `pattern_catalog('pattern')`."""
    th = th or Thresholds()
    d = describe_candles(df, th)
    s: dict[str, pd.Series] = {}

    # ---- Một nến ----
    pos = d["rng"] > 0
    s["doji"] = d["doji"]
    s["dragonfly_doji"] = d["doji"] & (d["upper_pct"] <= th.shadow_tiny) & (d["lower_pct"] >= th.long_shadow_pct)
    s["gravestone_doji"] = d["doji"] & (d["lower_pct"] <= th.shadow_tiny) & (d["upper_pct"] >= th.long_shadow_pct)
    s["long_legged_doji"] = d["doji"] & (d["upper_pct"] >= th.legged_pct) & (d["lower_pct"] >= th.legged_pct)

    maru = d["long_body"] & (d["upper_pct"] <= th.marubozu_shadow) & (d["lower_pct"] <= th.marubozu_shadow)
    s["marubozu_white"] = maru & d["white"]
    s["marubozu_black"] = maru & d["black"]

    s["spinning_top"] = (
        d["short_body"] & ~d["doji"] & (d["upper"] > d["body"]) & (d["lower"] > d["body"])
    )

    up1, down1 = _trend_flags(d, th, 1)
    hammer_shape = (
        pos & ~d["doji"] & (d["lower"] >= th.shadow_long_mult * d["body"]) & (d["upper_pct"] <= th.shadow_tiny)
    )
    inverted_shape = (
        pos & ~d["doji"] & (d["upper"] >= th.shadow_long_mult * d["body"]) & (d["lower_pct"] <= th.shadow_tiny)
    )
    s["hammer"] = hammer_shape & down1
    s["hanging_man"] = hammer_shape & up1
    s["inverted_hammer"] = inverted_shape & down1
    s["shooting_star"] = inverted_shape & up1

    # ---- Hai nến (nến 1 = t-1, nến 2 = t) ----
    up2, down2 = _trend_flags(d, th, 2)
    white1 = d["white"].shift(1, fill_value=False)
    black1 = d["black"].shift(1, fill_value=False)
    long1 = d["long_body"].shift(1, fill_value=False)
    o1, c1 = d["open"].shift(1), d["close"].shift(1)
    h1, l1 = d["high"].shift(1), d["low"].shift(1)
    top1, bot1, body1 = d["body_top"].shift(1), d["body_bot"].shift(1), d["body"].shift(1)
    mid1 = (o1 + c1) / 2

    engulf = (d["body_top"] >= top1) & (d["body_bot"] <= bot1) & (d["body"] > body1)
    inside = (d["body_top"] <= top1) & (d["body_bot"] >= bot1) & (d["body"] < body1)
    open_below = l1 if th.strict_gap else c1   # Piercing: mở cửa thấp hơn
    open_above = h1 if th.strict_gap else c1   # Dark Cloud: mở cửa cao hơn

    s["bullish_engulfing"] = down2 & black1 & d["white"] & engulf
    s["bearish_engulfing"] = up2 & white1 & d["black"] & engulf
    s["piercing"] = (
        down2 & black1 & long1 & d["white"]
        & (d["open"] < open_below) & (d["close"] > mid1) & (d["close"] < o1)
    )
    s["dark_cloud_cover"] = (
        up2 & white1 & long1 & d["black"]
        & (d["open"] > open_above) & (d["close"] < mid1) & (d["close"] > o1)
    )
    s["bullish_harami"] = down2 & black1 & long1 & d["white"] & inside
    s["bearish_harami"] = up2 & white1 & long1 & d["black"] & inside

    # ---- Ba nến: nến 3 xác nhận sau hai nến đầu (setup ở t-1) ----
    morning_setup, evening_setup = _star_setups(d, th)
    mid_c1 = ((d["open"] + d["close"]) / 2).shift(2)   # điểm giữa thân nến 1
    s["morning_star"] = morning_setup.shift(1, fill_value=False) & d["white"] & (d["close"] > mid_c1)
    s["evening_star"] = evening_setup.shift(1, fill_value=False) & d["black"] & (d["close"] < mid_c1)

    names = pattern_catalog("pattern")["name"].tolist()
    return pd.DataFrame(s, index=df.index)[names].astype(bool)


def detect_setups(df: pd.DataFrame, th: Thresholds | None = None) -> pd.DataFrame:
    """Cảnh báo sớm: phiên t đã có 2 nến đầu của Sao mai/Sao hôm, chờ nến 3 ở phiên t+1."""
    th = th or Thresholds()
    d = describe_candles(df, th)
    morning, evening = _star_setups(d, th)
    out = pd.DataFrame({"morning_star_setup": morning, "evening_star_setup": evening}, index=df.index)
    return out[pattern_catalog("setup")["name"].tolist()].astype(bool)


def to_events(signals: pd.DataFrame) -> pd.DataFrame:
    """Chuyển bảng tín hiệu bool sang dạng dài: mỗi dòng là một lần xuất hiện (date, pattern, bias, candles)."""
    cat = pattern_catalog().set_index("name")
    rows = []
    for name in signals.columns:
        for date in signals.index[signals[name].to_numpy()]:
            rows.append((date, name, cat.at[name, "bias"], int(cat.at[name, "candles"])))
    out = pd.DataFrame(rows, columns=["date", "pattern", "bias", "candles"])
    return out.sort_values(["date", "pattern"]).reset_index(drop=True)
