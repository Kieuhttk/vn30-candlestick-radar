"""Tần suất hoàn thành setup Sao mai/Sao hôm ở đúng phiên thị trường kế tiếp."""
from statistics import NormalDist

import numpy as np
import pandas as pd

from analytics.radar import build_radar

PAIRS = {
    "morning_star_setup": ("morning_star", "Sao mai"),
    "evening_star_setup": ("evening_star", "Sao hôm"),
}
OUTCOME_COLS = ["symbol", "setup", "setup_date", "next_date", "status"]


def wilson_interval(successes, total, confidence=0.95):
    if not 0 < confidence < 1:
        raise ValueError("confidence phải nằm giữa 0 và 1")
    if total < 0 or not 0 <= successes <= total:
        raise ValueError("Cần 0 <= successes <= total")
    if total == 0:
        return np.nan, np.nan
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def build_setup_outcomes(frames, asof, issues=None, th=None, market_days=None):
    radar = (build_radar(frames, asof, issues, th) if market_days is None else
             build_radar(frames, asof, issues, th, market_days=market_days))
    events = radar.events
    setups = events[events["kind"] == "setup"]
    confirmed = set(events.loc[events["kind"] == "pattern", ["symbol", "date", "name"]].itertuples(index=False, name=None))
    blocked = set()
    if issues is not None and not issues.empty:
        errors = issues[issues["severity"] == "error"]
        blocked = set(zip(errors["symbol"], pd.to_datetime(errors["trading_date"])))
    rows = []
    for event in setups.itertuples(index=False):
        if event.name not in PAIRS:
            continue
        position = radar.market_days.get_loc(event.date)
        next_date = pd.NaT
        if position + 1 == len(radar.market_days):
            status = "pending"
        else:
            next_date = radar.market_days[position + 1]
            frame = frames[event.symbol]
            if next_date not in frame.index:
                status = "missing_next_bar"
            else:
                o, h, l, c = frame.loc[next_date, ["open", "high", "low", "close"]].to_numpy(dtype=float)
                valid = (
                    np.isfinite([o, h, l, c]).all()
                    and min(o, h, l, c) > 0
                    and h >= max(o, c) and l <= min(o, c)
                    and (event.symbol, next_date) not in blocked
                )
                if not valid:
                    status = "invalid_next_bar"
                else:
                    target = PAIRS[event.name][0]
                    status = "completed" if (event.symbol, next_date, target) in confirmed else "not_completed"
        rows.append((event.symbol, event.name, event.date, next_date, status))
    return pd.DataFrame(rows, columns=OUTCOME_COLS)


def summarize_setups(outcomes, confidence=0.95):
    rows = []
    for name, (_, label) in PAIRS.items():
        counts = outcomes.loc[outcomes["setup"] == name, "status"].value_counts()
        successes = int(counts.get("completed", 0))
        evaluated = successes + int(counts.get("not_completed", 0))
        pending = int(counts.get("pending", 0))
        excluded = int(counts.get("missing_next_bar", 0) + counts.get("invalid_next_bar", 0))
        low, high = wilson_interval(successes, evaluated, confidence)
        rows.append({
            "setup": name, "name_vi": label,
            "n_total": int(counts.sum()), "n_evaluated": evaluated,
            "n_completed": successes, "n_pending": pending, "n_excluded": excluded,
            "probability": successes / evaluated if evaluated else np.nan,
            "ci_low": low, "ci_high": high,
        })
    return pd.DataFrame(rows)
