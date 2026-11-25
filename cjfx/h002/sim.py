"""H002 trade simulation on M1 bid bars (spec 3.3 + v0.6 B-1, B-4, M-3, M-4, M-6)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import NS_D, NS_H, NS_MIN, Bars, Instrument, flat_time, in_weekend_window, overlapping_gap

TARGET_R = 3.0
BUFFER_ATR = 0.10
MIN_STOP_COST_MULT = 3.0


def rollovers(a: int, b: int, weekend_trading: bool) -> int:
    """Swap nights between a and b: 17:00 New York rollovers crossed, Wednesday counts 3 (v0.6 M-12)."""
    if b <= a:
        return 0
    days = pd.date_range(pd.Timestamp(a, tz="UTC").tz_convert("America/New_York").normalize(),
                         pd.Timestamp(b, tz="UTC").tz_convert("America/New_York").normalize() + pd.Timedelta(days=1),
                         freq="D")
    n = 0
    for d in days:
        r = (d + pd.Timedelta(hours=17)).tz_convert("UTC").value
        if a < r <= b:
            if not weekend_trading and d.dayofweek >= 5:
                continue
            n += 3 if (d.dayofweek == 2 and not weekend_trading) else 1
    return n


def plan_trade(sig: dict, m1: Bars, spr_m1: np.ndarray, spread_at, inst: Instrument,
               buffer_atr: float = BUFFER_ATR, slip_mult: float = 1.0, enforce_min_stop: bool = True) -> dict:
    """Entry, stop, target for a reclaim signal, or a skip reason. spread_at(ns, bid) -> spread."""
    long = sig["side"] == "low"
    te = sig["reclaim_close_t"]
    e = int(np.searchsorted(m1.t, te, "left"))
    if e >= len(m1.t):
        return {"skip": "no_data_after"}
    t_entry = int(m1.t[e])
    if in_weekend_window(t_entry, inst):
        return {"skip": "weekend_window"}
    bid_o = m1.o[e]
    slip = inst.slip(bid_o) * slip_mult
    spr_reclaim = float(np.asarray(spread_at(np.array([te - NS_MIN]), np.array([sig["close"]]))[0]).ravel()[0])
    spr_e = spr_m1[e]
    buf = buffer_atr * sig["atr"]
    if not np.isfinite(buf):
        return {"skip": "atr_warmup"}
    if long:
        entry = bid_o + spr_e + slip
        stop = sig["extreme"] - buf - spr_reclaim
        R = entry - stop
    else:
        entry = bid_o - slip
        stop = sig["extreme"] + buf + spr_reclaim
        R = stop - entry
    rt_cost = spr_reclaim + 2 * slip
    if R <= 0:
        return {"skip": "entry_beyond_stop", "e": e, "t_entry": t_entry}
    if enforce_min_stop and R < MIN_STOP_COST_MULT * rt_cost:
        return {"skip": "stop_too_small", "e": e, "t_entry": t_entry, "entry": entry, "stop": stop, "R": R}
    target = entry + TARGET_R * R if long else entry - TARGET_R * R
    # entry bar already beyond target (gap) -> skip (v0.6 M-4)
    if (long and bid_o >= target) or (not long and bid_o + spr_e <= target):
        return {"skip": "entry_beyond_target", "e": e, "t_entry": t_entry}
    return {"e": e, "t_entry": t_entry, "entry": entry, "stop": stop, "target": target, "R": R, "long": long,
            "slip": slip, "spr_entry": spr_e, "spr_reclaim": spr_reclaim}


def run_trade(plan: dict, m1: Bars, spr_m1: np.ndarray, inst: Instrument) -> dict:
    """Walk M1 bars from entry to stop / target / weekly flat (fills per v0.6 B-4)."""
    e, long, stop, target, slip = plan["e"], plan["long"], plan["stop"], plan["target"], plan["slip"]
    tf = flat_time(plan["t_entry"], inst)
    f = int(np.searchsorted(m1.t, tf, "left"))
    sl = slice(e, max(f, e + 1))
    if long:
        stop_hit = m1.l[sl] <= stop
        tgt_hit = m1.h[sl] >= target
    else:
        ask_h = m1.h[sl] + spr_m1[sl]
        ask_l = m1.l[sl] + spr_m1[sl]
        stop_hit = ask_h >= stop
        tgt_hit = ask_l <= target
    js = int(np.argmax(stop_hit)) if stop_hit.any() else None
    jt = int(np.argmax(tgt_hit)) if tgt_hit.any() else None
    if js is not None and (jt is None or js <= jt):          # same M1 bar -> stop
        j = e + js
        if long:
            fill = min(stop, m1.o[j]) - slip
        else:
            ask_o = m1.o[j] + spr_m1[j]
            fill = max(stop, ask_o) + slip
        outcome, t_exit = "stop", int(m1.t[j]) + NS_MIN
    elif jt is not None:
        j = e + jt
        fill, outcome, t_exit = target, "target", int(m1.t[j]) + NS_MIN
    else:
        if f >= len(m1.t):
            j = len(m1.t) - 1
            outcome = "data_end"
            px = m1.c[j]
            t_exit = int(m1.t[j]) + NS_MIN
            fill = px - slip if long else px + spr_m1[j] + slip
        else:
            j = f
            outcome = "weekly_flat"
            t_exit = int(m1.t[j])
            fill = m1.o[j] - slip if long else m1.o[j] + spr_m1[j] + slip
    r = (fill - plan["entry"]) / plan["R"] if long else (plan["entry"] - fill) / plan["R"]
    return {"outcome": outcome, "t_exit": t_exit, "exit": fill, "r": r}


def simulate_cell(signals: list[dict], m1: Bars, spr_m1: np.ndarray, spread_at, inst: Instrument, gaps: np.ndarray,
                  buffer_atr: float = BUFFER_ATR, slip_mult: float = 1.0, fixed_list: set | None = None) -> pd.DataFrame:
    """One position at a time. With fixed_list, only those signal ids are traded and no re-selection happens
    (sensitivity re-pricing, v0.6 M-3)."""
    rows = []
    busy_until = -1
    for s in sorted(signals, key=lambda x: (x["reclaim_close_t"], x["sweep_t"])):
        row = {k: s[k] for k in ("sid", "lid", "source", "side", "level", "touches", "sweep_t", "reclaim_close_t",
                                 "extreme", "atr", "pd_state", "aligned", "sweep_to_reclaim", "gap_sweep",
                                 "spread_extrapolated", "close", "open_", "rng", "vol_pct", "trend",
                                 "ev1", "ev4", "ev12", "ev24") if k in s}
        if fixed_list is not None:
            if s["sid"] not in fixed_list:
                continue
        elif s["reclaim_close_t"] < busy_until:
            row["status"] = "position_open"
            rows.append(row)
            continue
        if s.get("tie_loser"):
            row["status"] = "signalled_not_executed"
            rows.append(row)
            continue
        p = plan_trade(s, m1, spr_m1, spread_at, inst, buffer_atr, slip_mult, enforce_min_stop=fixed_list is None)
        if "skip" in p:
            row["status"] = p["skip"]
            if p["skip"] == "stop_too_small":
                q = dict(p, long=s["side"] == "low", target=(p["entry"] + 3 * p["R"]) if s["side"] == "low" else (p["entry"] - 3 * p["R"]),
                         slip=inst.slip(m1.o[p["e"]]) * slip_mult)
                row["hyp_r"] = run_trade(q, m1, spr_m1, inst)["r"]
            rows.append(row)
            continue
        res = run_trade(p, m1, spr_m1, inst)
        g = overlapping_gap(gaps, s["sweep_t"], res["t_exit"])
        if g is not None:
            row["status"] = "data_gap"
            busy_until = max(res["t_exit"], g)
            rows.append(row)
            continue
        row.update(status="executed", t_entry=p["t_entry"], entry=p["entry"], stop=p["stop"], target=p["target"],
                   R=p["R"], spr_entry=p["spr_entry"], **res,
                   nights=rollovers(p["t_entry"], res["t_exit"], inst.weekend_trading),
                   hold_h=(res["t_exit"] - p["t_entry"]) / NS_H)
        busy_until = res["t_exit"]
        rows.append(row)
    return pd.DataFrame(rows)
