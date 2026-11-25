"""Build M5, H1, H4, D, W, MN bid/ask bars from M1, on the New York 17:00 trading calendar.

Every bar has: index = open time (UTC), columns open_time, close_time, bid_o..bid_c, ask_o..ask_c.
* M5 / H1: UTC clock buckets (17:00 New York is always on the hour). close = open + period.
* H4: anchored at the day boundary (17:00, 21:00, 01:00 ... New York, DST-aware) or UTC
  (calendar.h4_anchor). close = open + 4h.
* D: trading day from day_bounds; close = that day's 17:00 New York.
* W: Monday..Sunday trading days, open = Sunday 17:00 New York (the Monday trading day start),
  close = the next week's open (usable from the next weekly candle, assumption 3).
* MN: trading days of a calendar month; open = start of the month's first calendar trading day,
  close = start of next month.
Bars only exist where M1 data exists (no synthetic filler bars).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..calendar import day_bounds, parse_hhmm, trading_day

COLS = ["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]
AGG = {"bid_o": "first", "bid_h": "max", "bid_l": "min", "bid_c": "last",
       "ask_o": "first", "ask_h": "max", "ask_l": "min", "ask_c": "last"}


def _agg(m1: pd.DataFrame, key_ns: np.ndarray, close_ns: np.ndarray) -> pd.DataFrame:
    """Aggregate M1 rows by bar-open key (int64 ns). close_ns aligned to rows (bar close per row)."""
    g = m1[COLS].groupby(key_ns, sort=True)
    out = g.agg(AGG)
    cl = pd.Series(close_ns).groupby(key_ns).max()
    idx = pd.DatetimeIndex(pd.to_datetime(out.index.to_numpy(), utc=True), name="time")
    out.index = idx
    out.insert(0, "close_time", pd.DatetimeIndex(pd.to_datetime(cl.to_numpy(), utc=True)))
    out.insert(0, "open_time", idx)
    return out


def _fixed(m1: pd.DataFrame, freq: str) -> pd.DataFrame:
    op = m1.index.floor(freq)
    k = op.as_unit("ns").asi8
    return _agg(m1, k, k + pd.Timedelta(freq).value)


def _h4(m1: pd.DataFrame, cal: dict) -> pd.DataFrame:
    if cal.get("h4_anchor", "day_boundary") == "utc":
        return _fixed(m1, "4h")
    b = cal["day_boundary"]
    t = parse_hhmm(b["time"])
    off = pd.Timedelta(hours=t.hour, minutes=t.minute)
    local = m1.index.tz_convert(b["tz"]).tz_localize(None) - off
    into = (local - local.floor("4h")).to_numpy()          # time since bucket start, wall clock
    op = (m1.index - pd.to_timedelta(into)).floor("min")
    k = op.as_unit("ns").asi8
    return _agg(m1, k, k + pd.Timedelta("4h").value)


def _calendar_bars(m1: pd.DataFrame, cal: dict, labels: pd.DatetimeIndex, next_labels: pd.DatetimeIndex,
                   first_days: pd.DatetimeIndex) -> pd.DataFrame:
    """labels: per-row period label (tz-naive). first_days / next_labels per row: first trading-day
    label of this period and of the next period, used for nominal open/close."""
    b = cal["day_boundary"]
    open_utc, _ = day_bounds(first_days, b)
    close_utc, _ = day_bounds(next_labels, b)
    k = open_utc.as_unit("ns").asi8
    return _agg(m1, k, close_utc.as_unit("ns").asi8)


def build_all(m1: pd.DataFrame, cal: dict) -> dict[str, pd.DataFrame]:
    m1 = m1[COLS].sort_index()
    m1 = m1[~m1.index.duplicated(keep="last")]
    out = {"M1": m1, "M5": _fixed(m1, "5min"), "H1": _fixed(m1, "1h"), "H4": _h4(m1, cal)}
    b = cal["day_boundary"]
    td = trading_day(m1.index, b)
    # D
    s, e = day_bounds(td, b)
    out["D"] = _agg(m1, s.as_unit("ns").asi8, e.as_unit("ns").asi8)
    # W: weeks of Monday..Sunday trading days
    mon = td - pd.to_timedelta(td.dayofweek, unit="D")
    out["W"] = _calendar_bars(m1, cal, mon, mon + pd.Timedelta(days=7), mon)
    # MN
    ms = td.to_period("M").to_timestamp()
    nxt = (td.to_period("M") + 1).to_timestamp()
    out["MN"] = _calendar_bars(m1, cal, ms, nxt, ms)
    return out


def quality_report(m1: pd.DataFrame, cal: dict, gap_limit_min: int = 30) -> dict:
    idx = m1.index
    d = np.diff(idx.as_unit("ns").asi8) / 60e9
    ny = idx[:-1].tz_convert(cal["day_boundary"]["tz"])
    # ignore gaps that start Friday afternoon (weekend) or around the daily 17:00 break
    weekendish = (ny.dayofweek >= 4) & ((ny.dayofweek > 4) | (ny.hour >= 15))
    rollover = (ny.hour == 16) | (ny.hour == 17)
    big = (d > gap_limit_min) & ~weekendish & ~rollover
    sp = (m1["ask_c"] - m1["bid_c"])
    return {"m1_bars": int(len(m1)), "first": idx.min(), "last": idx.max(),
            "gaps_over_limit_in_trading_time": int(big.sum()),
            "largest_gaps_min": sorted(d[big].round(0).tolist(), reverse=True)[:5],
            "bid_only_source": bool((sp == 0).mean() > 0.99),
            "bars_per_year": {int(y): int(n) for y, n in pd.Series(1, index=idx).groupby(idx.year).sum().items()}}
