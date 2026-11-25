"""Liquidity levels L on H1, in direction space (lows; shorts use mirrored highs).

Each function returns an array: L[s] is the level available at the *open* of H1 bar s,
or NaN when no unswept level of that type exists. A level counts as swept (and is no
longer liquidity) once any H1 low trades below it before bar s.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calendar import session_bounds, trading_day
from .indicators import swing_lows
from .market import Market

MAX_ACTIVE = 64


def _unswept_swing_lows(l: np.ndarray, k: int):
    """Yield, for each bar s, the list of (index, level) confirmed and unswept before s."""
    sl = swing_lows(l, k)
    active: list[tuple[int, float]] = []
    for s in range(len(l)):
        if s >= 1:
            prev = l[s - 1]
            active = [(i, v) for (i, v) in active if prev >= v]
        i = s - 1 - k
        if i >= 0 and sl[i]:
            active.append((i, float(l[i])))
            if len(active) > MAX_ACTIVE:
                active = active[-MAX_ACTIVE:]
        yield s, active


def h1_swing(mkt: Market, fx: dict) -> np.ndarray:
    h1 = mkt.tf["H1"]
    out = np.full(len(h1), np.nan)
    for s, active in _unswept_swing_lows(h1.l, fx["swing_k"]["h1"]):
        if active:
            out[s] = active[-1][1]
    return out


def equal_levels(mkt: Market, fx: dict) -> np.ndarray:
    h1 = mkt.tf["H1"]
    out = np.full(len(h1), np.nan)
    tol_k = fx["equal_levels_tol_atr_h1"]
    look = fx["equal_levels_lookback_h1_bars"]
    for s, active in _unswept_swing_lows(h1.l, fx["swing_k"]["h1"]):
        if len(active) < 2 or s == 0:
            continue
        tol = tol_k * h1.atr[s - 1]
        if np.isnan(tol):
            continue
        recent = [(i, v) for (i, v) in active if i >= s - look]
        best = None
        # most recent pair of swing lows within tolerance; L = the lower one
        for a in range(len(recent) - 1, 0, -1):
            for b in range(a - 1, -1, -1):
                if abs(recent[a][1] - recent[b][1]) <= tol:
                    best = min(recent[a][1], recent[b][1])
                    break
            if best is not None:
                break
        if best is not None:
            out[s] = best
    return out


def _running_min_since(l: np.ndarray, group: np.ndarray, start_mask: np.ndarray) -> np.ndarray:
    """Min of lows strictly before bar s, counted from the first bar where start_mask is
    True within the same group. NaN before that point."""
    out = np.full(len(l), np.nan)
    cur = np.nan
    g_prev = None
    started = False
    for s in range(len(l)):
        if group[s] != g_prev:
            g_prev = group[s]
            cur = np.nan
            started = False
        out[s] = cur
        if start_mask[s]:
            started = True
        if started:
            cur = l[s] if np.isnan(cur) else min(cur, l[s])
    return out


def prev_day(mkt: Market, cal: dict) -> np.ndarray:
    h1 = mkt.tf["H1"]
    d = mkt.tf["D"]
    t_open = pd.to_datetime(h1.t_open, utc=True)
    days = trading_day(pd.DatetimeIndex(t_open), cal["day_boundary"]).as_unit('ns').asi8
    # previous day's low = last D bar closed by the open of s
    di = np.searchsorted(d.t_close, h1.t_open, side="right") - 1
    pdl = np.where(di >= 0, d.l[np.clip(di, 0, None)], np.nan)
    swept_min = _running_min_since(h1.l, days, np.ones(len(h1), dtype=bool))
    out = np.where(np.isnan(swept_min) | (swept_min >= pdl), pdl, np.nan)
    return out


def asian_session(mkt: Market, cal: dict) -> np.ndarray:
    h1 = mkt.tf["H1"]
    t_open = pd.DatetimeIndex(pd.to_datetime(h1.t_open, utc=True))
    days = trading_day(t_open, cal["day_boundary"])
    uniq = days.unique()
    pos = uniq.get_indexer(days)
    s_start, s_end = session_bounds(uniq, cal["sessions"][cal["asian_range_session"]], cal["day_boundary"])
    st, en = s_start.as_unit('ns').asi8[pos], s_end.as_unit('ns').asi8[pos]
    t = h1.t_open
    inside = (t >= st) & ((t + 3600 * 10**9) <= en)
    after = t >= en
    lows = pd.Series(np.where(inside, h1.l, np.nan)).groupby(pos).transform("min").to_numpy()
    swept_min = _running_min_since(h1.l, pos, after)
    level = np.where(after, lows, np.nan)
    ok = np.isnan(swept_min) | (swept_min >= level)
    return np.where(ok, level, np.nan)


def compute(mkt: Market, cfg: dict, kind: str) -> np.ndarray:
    fx, cal = cfg["fixed_for_now"], cfg["calendar"]
    if kind == "h1_swing":
        return h1_swing(mkt, fx)
    if kind == "equal_levels":
        return equal_levels(mkt, fx)
    if kind == "prev_day":
        return prev_day(mkt, cal)
    if kind == "asian_session":
        return asian_session(mkt, cal)
    raise ValueError(kind)
