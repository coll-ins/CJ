"""Trade simulation on 1-minute bid/ask bars with stop, target, trailing and partial exits.

Conventions (direction space, so the same code serves longs and shorts):
  * entry fills at the entry-side open of the first M1 bar at the entry time, plus slippage;
  * stops and targets trigger on the exit side (bid for longs, ask for shorts);
  * a stop that is gapped through fills at the bar open; slippage is added to stop and
    market exits, not to targets (resting limit orders);
  * if one M1 bar touches both stop and target, the stop is assumed (conservative);
  * R = entry fill - initial stop. Results are in R after spread, slippage and swap.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .calendar import day_bounds, trading_day
from .engine import ExecContext, Setup
from .market import Market
from .zones import Zone

INF = np.iinfo(np.int64).max


@dataclass
class Trade:
    entry_time: int
    exit_time: int
    entry: float
    stop: float
    target: float
    r_dist: float
    r_mult: float
    exit_reason: str
    spread_at_entry: float
    swap_r: float


def _first_hit(xl, xh, start, end, stop, target):
    j = start
    chunk = 2048
    while j < end:
        e = min(end, j + chunk)
        hs = xl[j:e] <= stop
        ht = xh[j:e] >= target
        m = hs | ht
        if m.any():
            k = int(np.argmax(m))
            return j + k, bool(hs[k])
        j = e
        chunk *= 2
    return None, False


def forced_exit_time(entry_time: int, cfg: dict) -> int:
    """Start of the last M5 bar before the trading-day boundary that follows entry."""
    cal = cfg["calendar"]
    ts = pd.DatetimeIndex(pd.to_datetime([entry_time], utc=True))
    day = trading_day(ts, cal["day_boundary"])
    _, end = day_bounds(day, cal["day_boundary"])
    return int(end.as_unit('ns').asi8[0] - 5 * 60 * 10**9)


def nights_held(t_in: int, t_out: int, cfg: dict) -> float:
    cal = cfg["calendar"]
    days = trading_day(pd.DatetimeIndex(pd.to_datetime([t_in, t_out], utc=True)), cal["day_boundary"])
    if days[1] <= days[0]:
        return 0.0
    labels = pd.date_range(days[0], days[1] - pd.Timedelta(days=1), freq="D")  # day ends crossed
    wd = cfg["costs"].get("triple_swap_weekday", 2)
    # rollover at the end of trading day labelled X happens on calendar weekday of X-1 evening
    rollover_wd = (labels - pd.Timedelta(days=1)).dayofweek
    w = np.where(rollover_wd == wd, 3.0, 1.0)
    w[np.asarray(labels.dayofweek) >= 5] = 0.0  # no weekend-day rollovers (no trading days)
    return float(w.sum())


def opposing_target(entry: float, t: int, opp: list[Zone]) -> float:
    """Nearest edge of an active opposing zone above entry (direction space)."""
    best = np.inf
    for z in opp:
        if z.created_time <= t < z.dead_time:
            edge = -z.top  # opposing zone found in mirrored space; its near edge mapped back
            if entry < edge < best:
                best = edge
    return best


def simulate(st: Setup, stop_mode: str, exit_mode: str, mkt: Market, ctx: ExecContext,
             opp_zones: list[Zone], cfg: dict) -> Trade | str:
    fx, costs = cfg["fixed_for_now"], cfg["costs"]
    m1 = mkt.tf["M1"]
    pip = mkt.pip
    sl = costs["slippage_pips_per_side"]
    slip = (sl[mkt.pair] if isinstance(sl, dict) else sl) * pip
    i = m1.idx_open_at_or_after(st.entry_time)
    if i >= len(m1):
        return "no_data"
    end = len(m1)
    if st.execution == "intraday_m5":
        tf = forced_exit_time(st.entry_time, cfg)
        if st.entry_time >= tf:
            return "after_intraday_cutoff"
        end = m1.idx_open_at_or_after(tf)
        if end <= i:
            return "after_intraday_cutoff"
    entry = m1.eo[i] + slip
    spread = m1.eo[i] - m1.xo[i]
    buf = fx["stop_buffer_atr_h1"] * st.atr_h1 + spread
    base = st.sweep_low if stop_mode == "sweep_wick" else st.conf_swing_low
    stop = base - buf
    r = entry - stop
    if not r > 0:
        return "stop_above_entry"
    if r < fx["stop_min_atr_h1"] * st.atr_h1:
        return "stop_too_small"
    if r > fx["stop_max_atr_h4"] * st.atr_h4:
        return "stop_too_large"
    tr = fx["target_r"]
    xl, xh, xo = m1.xl, m1.xh, m1.xo

    def stop_fill(j, lvl):
        return min(lvl, xo[j]) - slip

    def market_exit(j):
        if j >= len(m1):
            j = len(m1) - 1
            return float(m1.xc[j] - slip), int(m1.t_close[j]), "data_end"
        return float(xo[j] - slip), int(m1.t_open[j]), "time_exit"

    if exit_mode in ("fixed_3r", "extended"):
        target = entry + tr * r
        if exit_mode == "extended":
            edge = opposing_target(entry, st.entry_time, opp_zones)
            if np.isfinite(edge) and edge - entry >= tr * r:
                target = min(edge, entry + fx["extended_target_cap_r"] * r)
        j, is_stop = _first_hit(xl, xh, i, end, stop, target)
        if j is None:
            px, t_out, why = market_exit(end)
        elif is_stop:
            px, t_out, why = stop_fill(j, stop), int(m1.t_open[j]), "stop"
        else:
            px, t_out, why = max(target, xo[j]), int(m1.t_open[j]), "target"
        pnl = px - entry
        parts_done = pnl
    elif exit_mode in ("trailing", "partial"):
        trigger = entry + fx["trail_start_r"] * r
        j, is_stop = _first_hit(xl, xh, i, end, stop, trigger)
        target = np.nan
        if j is None or is_stop:
            if j is None:
                px, t_out, why = market_exit(end)
            else:
                px, t_out, why = stop_fill(j, stop), int(m1.t_open[j]), "stop"
            parts_done = px - entry
        else:
            frac = fx["partial_fraction"] if exit_mode == "partial" else 0.0
            banked = frac * (max(trigger, xo[j]) - entry)
            cur = entry if exit_mode == "partial" else entry + fx["trail_lock_r"] * r
            t_trig = int(m1.t_close[j])
            # new execution-TF swing lows confirmed after the trigger move the stop up
            E = ctx.s
            k = ctx.k
            sl = ctx.sl_idx
            conf_t = E.t_close[np.clip(sl + k, 0, len(E) - 1)]
            sel = (sl + k < len(E)) & (conf_t >= t_trig)
            updates = sorted(zip(conf_t[sel].tolist(), E.l[sl[sel]].tolist()))
            pos = j + 1
            ui = 0
            hit = None
            while pos < end:
                nxt_t = updates[ui][0] if ui < len(updates) else INF
                seg_end = min(end, m1.idx_open_at_or_after(nxt_t)) if nxt_t != INF else end
                if seg_end > pos:
                    h, _ = _first_hit(xl, xh, pos, seg_end, cur, np.inf)
                    if h is not None:
                        hit = h
                        break
                    pos = seg_end
                if ui >= len(updates):
                    break
                cand = updates[ui][1] - fx["stop_buffer_atr_h1"] * st.atr_h1 - (m1.eo[min(pos, len(m1)-1)] - m1.xo[min(pos, len(m1)-1)])
                cur = max(cur, cand)
                ui += 1
            if hit is not None:
                px, t_out, why = stop_fill(hit, cur), int(m1.t_open[hit]), "trail_stop"
            else:
                px, t_out, why = market_exit(end)
            parts_done = banked + (1 - frac) * (px - entry)
    else:
        raise ValueError(exit_mode)
    swap_cfg = costs.get("swap_pips_per_night", {}).get(mkt.pair, {})
    sw = swap_cfg.get("long" if mkt.direction == 1 else "short", 0.0)
    swap_r = 0.0
    if sw:
        swap_r = sw * pip * nights_held(st.entry_time, t_out, cfg) / r
    return Trade(st.entry_time, t_out, float(entry), float(stop), float(target), float(r),
                 float(parts_done / r + swap_r), why, float(spread), float(swap_r))
