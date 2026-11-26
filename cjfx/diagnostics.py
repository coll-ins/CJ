"""Component diagnostics for H001 (descriptive research, not a strategy test).

1. Event studies: does each H001 step, ALONE, predict direction?
   For every event on bar i (in direction space, so longs and shorts pool), the forward move
       f = (close[i+h] - close[i]) / ATR14[i]
   is compared with a baseline matched on hour of week and direction: the mean f over ALL bars
   of the same series at the same UTC hour of week. Excess = f - baseline. Volatility is matched
   by the ATR scaling. Events are thinned so no two kept events of one direction are within h
   bars (non-overlapping), and the t-stat uses the thinned set. Prices are bid (no costs):
   this measures prediction, not tradability.
2. Trade paths (MFE): for each unique H001 setup, the maximum favourable excursion in R before
   the stop is hit (exit side, M1, after spread), and the expectancy of fixed targets.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import levels as levels_mod
from .indicators import last_confirmed_swing_high
from .market import Market, Series
from .zones import find_zones


def _how(s: Series) -> np.ndarray:
    t = pd.to_datetime(s.t_open, utc=True)
    return np.asarray(t.dayofweek * 24 + t.hour)


def forward(s: Series, h: int) -> np.ndarray:
    f = np.full(len(s), np.nan)
    f[:-h] = (s.c[h:] - s.c[:-h]) / s.atr[:-h]
    f[~np.isfinite(f)] = np.nan
    return f


def baseline(s: Series, f: np.ndarray) -> np.ndarray:
    how = _how(s)
    m = pd.Series(f).groupby(how).mean()
    return m.reindex(how).to_numpy()


def thin(idx: np.ndarray, h: int) -> np.ndarray:
    keep, last = [], -10**9
    for i in np.sort(idx):
        if i - last >= h:
            keep.append(i)
            last = i
    return np.array(keep, dtype=int)


def event_stats(events: dict[int, np.ndarray], series: dict[int, Series], h: int) -> dict:
    ex, exp = [], []
    for d, idx in events.items():
        s = series[d]
        f = forward(s, h)
        b = baseline(s, f)
        k = thin(idx[(idx >= 0) & (idx < len(s) - h)], h)
        e = (f - b)[k]
        ok = np.isfinite(e)
        ex.append(e[ok])
        exp.append((e * s.atr[k])[ok])
    x = np.concatenate(ex) if ex else np.array([])
    n = len(x)
    if n < 3:
        return {"n": n}
    sd = x.std(ddof=1)
    xp = np.concatenate(exp)
    return {"n": int(n), "excess_atr": float(x.mean()), "excess_price": float(xp.mean()), "t": float(x.mean() / (sd / np.sqrt(n))) if sd > 0 else np.nan,
            "hit_rate_vs_base": float((x > 0).mean())}


def component_events(pair: str, bars: dict, cfg: dict) -> tuple[dict, dict]:
    """Returns ({component: {tf: ..., events: {d: idx}}}, {d: Market})."""
    fx = cfg["fixed_for_now"]
    mk = {d: Market(pair, bars, cfg, d) for d in (1, -1)}
    out = {}
    # 1. first touch of an H4 zone (consecutive_3 base), impulse 2.0 and 1.0
    for im in (2.0, 1.0):
        ev = {}
        for d, m in mk.items():
            h1 = m.tf["H1"]
            idx = []
            for z in find_zones(m.tf["H4"], {**fx, "impulse_atr_h4": im}, "consecutive_3"):
                s0 = h1.idx_open_at_or_after(z.created_time)
                hit = np.where(h1.l[s0:] <= z.top)[0]
                if len(hit):
                    i = s0 + hit[0]
                    if h1.t_close[i] <= z.dead_time:
                        idx.append(i)
            ev[d] = np.array(idx, dtype=int)
        out[f"zone_first_touch_imp{im}"] = {"tf": "H1", "events": ev}
    # 2. sweep and close back above a liquidity level, same H1 bar, anywhere (no zone)
    for L in ("prev_day", "h1_swing", "asian_session"):
        ev = {}
        for d, m in mk.items():
            h1 = m.tf["H1"]
            lv = levels_mod.compute(m, cfg, L)
            ev[d] = np.where(np.isfinite(lv) & (h1.l < lv) & (h1.c > lv))[0]
        out[f"sweep_close_back_{L}"] = {"tf": "H1", "events": ev}
    # 3. MN/W bias alone: every H1 bar where monthly and weekly (last closed) are both with the trade
    for name, need in (("bias_mn_and_w", ("MN", "W")), ("bias_w_only", ("W",))):
        ev = {}
        for d, m in mk.items():
            h1 = m.tf["H1"]
            ok = np.ones(len(h1), dtype=bool)
            for tf in need:
                s = m.tf[tf]
                i = np.searchsorted(s.t_close, h1.t_open, side="right") - 1
                st = np.where(i >= 0, m.state[tf][np.clip(i, 0, None)], 0)
                ok &= st == 1
            ev[d] = np.where(ok)[0]
        out[name] = {"tf": "H1", "events": ev}
    # 4. confirmation alone: close crosses above the last confirmed swing high (k from config)
    for tf in ("H1", "M5"):
        ev = {}
        for d, m in mk.items():
            s = m.tf[tf]
            lsh = last_confirmed_swing_high(s.h, fx["swing_k"][tf.lower()])
            cross = (s.c > lsh) & np.r_[False, ~(s.c[:-1] > lsh[:-1])]
            ev[d] = np.where(cross & np.isfinite(lsh))[0]
        out[f"swing_break_{tf}"] = {"tf": tf, "events": ev}
    return out, mk


HORIZONS = {"H1": (4, 12, 24), "M5": (12, 48, 144)}


def run_components(pair: str, bars: dict, cfg: dict) -> pd.DataFrame:
    comps, mk = component_events(pair, bars, cfg)
    rows = []
    for name, c in comps.items():
        series = {d: m.tf[c["tf"]] for d, m in mk.items()}
        for h in HORIZONS[c["tf"]]:
            r = event_stats(c["events"], series, h)
            rows.append({"pair": pair, "component": name, "tf": c["tf"], "horizon_bars": h,
                         "raw_events": int(sum(len(v) for v in c["events"].values())), **r})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ trade paths

def mfe_table(trades: pd.DataFrame, mk: dict, cfg: dict, swing_days: int = 10) -> pd.DataFrame:
    """One row per trade: R reached before the stop (exit side, M1) and the mark-to-market R at the
    horizon end (intraday: entry day's 17:00 New York close; swing: swing_days later)."""
    from .calendar import day_bounds, trading_day
    rows = []
    for _, t in trades.iterrows():
        d = int(t["direction"])
        m1 = mk[d].tf["M1"]
        e, stp = t["entry"] * d, t["stop_px"] * d
        r = e - stp
        if not r > 0:
            continue
        t0 = pd.Timestamp(t["entry_time"]).value
        if t["execution"] == "intraday_m5":
            td = trading_day(pd.DatetimeIndex([t["entry_time"]]), cfg["calendar"]["day_boundary"])
            _, end = day_bounds(td, cfg["calendar"]["day_boundary"])
            t1 = end[0].value
        else:
            t1 = t0 + swing_days * 86400 * 10**9
        i0 = m1.idx_open_at_or_after(t0)
        i1 = m1.idx_open_at_or_after(t1)
        if i1 <= i0:
            continue
        lo, hi = m1.xl[i0:i1], m1.xh[i0:i1]
        stop_hit = np.where(lo <= stp)[0]
        j = stop_hit[0] if len(stop_hit) else i1 - i0
        mfe = (hi[: j + 1].max() - e) / r if j < len(hi) else (hi.max() - e) / r
        # MFE strictly before the stop bar (same-bar ambiguity counts against the trade)
        mfe_before = (hi[:j].max() - e) / r if j > 0 else -np.inf
        end_r = -1.0 if len(stop_hit) else (m1.xc[i1 - 1] - e) / r
        rows.append({"pair": t["pair"], "execution": t["execution"], "setup_type": t["setup_type"],
                     "impulse_atr": t.get("impulse_atr"), "entry_time": t["entry_time"],
                     "mfe_R": float(mfe_before), "stopped": bool(len(stop_hit)), "end_R": float(end_r)})
    return pd.DataFrame(rows)


def target_expectancy(mfe: pd.DataFrame, targets=(0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)) -> pd.DataFrame:
    out = []
    for T in targets:
        r = np.where(mfe["mfe_R"] >= T, T, mfe["end_R"])
        n = len(r)
        sd = r.std(ddof=1) if n > 1 else np.nan
        out.append({"target_R": T, "n": n, "hit_rate": float((mfe["mfe_R"] >= T).mean()),
                    "expectancy_R": float(r.mean()), "t": float(r.mean() / (sd / np.sqrt(n))) if n > 1 and sd > 0 else np.nan})
    return pd.DataFrame(out)
