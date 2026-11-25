"""H001 setup scanner: zone -> first touch -> H1 sweep and close-back -> confirmation.

Pure functions of past data. Every decision at time t uses only bars closed by t.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .calendar import friday_cutoff_mask, in_sessions
from .indicators import swing_highs, swing_lows
from .market import Market, Series, setup_type
from .zones import Zone

HOUR = 3600 * 10**9
EXEC_TF = {"swing_h1": "H1", "intraday_m5": "M5"}


@dataclass
class Setup:
    pair: str
    direction: int
    execution: str
    zone_id: int
    zone_top: float
    zone_bottom: float
    first_touch: int
    sweep_time: int
    level: float
    sweep_low: float
    confirm_time: int
    entry_time: int
    entry_e_idx: int
    conf_swing_high: float
    conf_swing_low: float
    atr_h1: float
    atr_h4: float
    bias_mn: int
    bias_w: int
    setup_type: str | None
    blocked: list = field(default_factory=list)


class ExecContext:
    """Precomputed execution-timeframe swing data."""

    def __init__(self, s: Series, k: int):
        self.s = s
        self.k = k
        self.sh_idx = np.where(swing_highs(s.h, k))[0]
        self.sl_idx = np.where(swing_lows(s.l, k))[0]

    def recent_swing_high(self, e: int, after_idx: int) -> int:
        """Most recent swing high confirmed by close of bar e-1 and formed after after_idx."""
        p = np.searchsorted(self.sh_idx, e - 1 - self.k, side="right") - 1
        if p < 0:
            return -1
        i = int(self.sh_idx[p])
        return i if i > after_idx else -1


class EntryFilter:
    def __init__(self, cfg: dict, session_names: list[str], pair: str, news: pd.DataFrame | None):
        self.cfg = cfg
        self.sessions = session_names
        fx = cfg["fixed_for_now"]
        self.fri = fx["friday_no_entry_after"]
        self.news_ns = None
        self.blackout = fx["news_blackout_minutes"] * 60 * 10**9
        if news is not None and len(news):
            ccy = {pair[:3], pair[3:]}
            ev = news[news["currency"].isin(ccy) & (news["impact"].str.lower() == "high")]
            self.news_ns = np.sort(pd.DatetimeIndex(ev["time_utc"]).as_unit('ns').asi8)

    def reasons(self, t: int) -> list[str]:
        ts = pd.DatetimeIndex(pd.to_datetime([t], utc=True))
        out = []
        if not in_sessions(ts, self.sessions, self.cfg["calendar"])[0]:
            out.append("session")
        if friday_cutoff_mask(ts, self.fri)[0]:
            out.append("friday_cutoff")
        if self.news_ns is not None and len(self.news_ns):
            p = np.searchsorted(self.news_ns, t)
            near = [self.news_ns[q] for q in (p - 1, p) if 0 <= q < len(self.news_ns)]
            if any(abs(t - x) <= self.blackout for x in near):
                out.append("news")
        return out


def scan_zone(z: Zone, mkt: Market, level: np.ndarray, execution: str, ctx: ExecContext,
              filt: EntryFilter, cfg: dict) -> Setup | None:
    fx = cfg["fixed_for_now"]
    h1, h4 = mkt.tf["H1"], mkt.tf["H4"]
    E = ctx.s
    n1 = len(h1)
    s0 = h1.idx_open_at_or_after(z.created_time)
    if s0 >= n1:
        return None
    # first touch: H1 low at or below the zone top, before the zone dies
    hit = np.where(h1.l[s0:] <= z.top)[0]
    if not len(hit):
        return None
    s0 = s0 + int(hit[0])
    if h1.t_open[s0] >= z.dead_time:
        return None
    t0 = int(h1.t_open[s0])
    t_limit = t0 + int(fx["time_limit_hours"][execution] * HOUR)
    # touch expiry: the zone dies at the start of touch number max_touches + 1
    dead = z.dead_time
    s_end = int(np.searchsorted(h1.t_open, t_limit, side="left"))
    seg = h1.l[s0:s_end] <= z.top
    starts = np.where(seg & ~np.r_[False, seg[:-1]])[0]
    mt = fx["zone_max_touches"]
    if len(starts) > mt:
        dead = min(dead, int(h1.t_open[s0 + starts[mt]]))
    sweep_cap = fx["sweep_max_above_zone_atr_h4"]
    cb_max = fx["close_back_max_h1_bars"]
    blocked: list = []
    s = s0
    while s < n1 and h1.t_close[s] <= t_limit and h1.t_open[s] < dead:
        L = level[s]
        if np.isnan(L) or not h1.l[s] < L:
            s += 1
            continue
        a4 = mkt.atr_at("H4", int(h1.t_open[s]))
        if np.isnan(a4) or h1.l[s] > z.top + sweep_cap * a4:
            s += 1
            continue
        cb = -1
        for q in range(s, min(n1, s + cb_max)):
            if h1.t_close[q] > t_limit or h1.c[q] < z.bottom:
                break
            if h1.c[q] > L:
                cb = q
                break
        if cb < 0:
            s += 1
            continue
        if h1.t_close[cb] > dead:
            break
        sweep_low = float(h1.l[s: cb + 1].min())
        # sweep-low bar on the execution timeframe
        if execution == "swing_h1":
            sl_e = s + int(np.argmin(h1.l[s: cb + 1]))
        else:
            a = E.idx_open_at_or_after(int(h1.t_open[s]))
            b = E.idx_open_at_or_after(int(h1.t_close[cb]))
            if b <= a:
                s = cb + 1
                continue
            sl_e = a + int(np.argmin(E.l[a:b]))
        e = E.idx_open_at_or_after(int(h1.t_close[cb]))
        result = None
        resume_t = None
        while e < len(E) and E.t_close[e] <= t_limit:
            if E.l[e] < sweep_low:
                resume_t = int(E.t_close[e])
                break
            i_sh = ctx.recent_swing_high(e, sl_e)
            if i_sh >= 0 and E.c[e] > E.h[i_sh]:
                result = (e, i_sh)
                break
            e += 1
        if result is None:
            if resume_t is None:
                break  # time limit reached
            s = max(cb + 1, h1.idx_open_at_or_after(resume_t))
            continue
        e, i_sh = result
        if e + 1 >= len(E):
            return None
        t_entry = int(E.t_open[e + 1])
        if t_entry >= dead:
            return None
        why = filt.reasons(t_entry)
        if why:
            blocked.append((t_entry, why))
            s = max(cb + 1, h1.idx_open_at_or_after(int(E.t_close[e])))
            continue
        mn, w = mkt.bias(t_entry)
        return Setup(
            pair=mkt.pair, direction=mkt.direction, execution=execution, zone_id=z.zid,
            zone_top=z.top, zone_bottom=z.bottom, first_touch=t0, sweep_time=int(h1.t_open[s]),
            level=float(L), sweep_low=sweep_low, confirm_time=int(E.t_close[e]), entry_time=t_entry,
            entry_e_idx=e + 1, conf_swing_high=float(E.h[i_sh]),
            conf_swing_low=float(E.l[i_sh + 1: e + 1].min()),
            atr_h1=mkt.atr_at("H1", t_entry), atr_h4=a4 if np.isnan(mkt.atr_at("H4", t_entry)) else mkt.atr_at("H4", t_entry),
            bias_mn=mn, bias_w=w, setup_type=setup_type(mn, w), blocked=blocked,
        )
    return None


def scan(zones: list[Zone], mkt: Market, level: np.ndarray, execution: str, ctx: ExecContext,
         filt: EntryFilter, cfg: dict) -> list[Setup]:
    out = []
    for z in zones:
        st = scan_zone(z, mkt, level, execution, ctx, filt, cfg)
        if st is not None:
            out.append(st)
    return out
