"""H002 runner: signals, trades, fixed-list sensitivities and placebos per instrument (spec v0.6)."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import engine as E
from .sim import simulate_cell

ROOT = Path(__file__).resolve().parents[2]
TFS = ("M5", "M15", "H1")
HIST_END = pd.Timestamp("2024-01-01", tz="UTC").value
EXPOSED_END = pd.Timestamp("2026-11-14", tz="UTC").value      # through 2026-11-13 (v0.6 m-11)
BTC_EXNESS_FROM = pd.Timestamp("2017-09-01", tz="UTC").value
EV_H = (1, 4, 12, 24)


def load_cfg() -> dict:
    return yaml.safe_load(open(ROOT / "config/h002.yaml"))


def load_m1(name: str) -> pd.DataFrame:
    m1 = pd.read_parquet(ROOT / f"data/m1/{name}_M1.parquet")
    if name == "BTCUSD":   # v0.6 M-11: Exness BTCUSDm bid from 2017-09-01, Binance before
        files = sorted((ROOT / "data/exness_m1/BTCUSDm").glob("*.parquet"))
        ex = pd.concat([pd.read_parquet(f) for f in files])
        ex.index = ex.index.as_unit("ns")
        cut = pd.Timestamp("2017-09-01", tz="UTC")
        m1.index = m1.index.as_unit("ns")
        m1 = pd.concat([m1[m1.index < cut], ex[ex.index >= cut]])
        m1 = m1[~m1.index.duplicated(keep="last")].sort_index()
    return m1


def spread_model(cfg, name, stat="median", mult=1.0):
    prof = pd.read_csv(ROOT / "results/h002/spread_profiles.csv")
    man = pd.read_csv(ROOT / "results/h002/cost_inputs.csv")
    series = cfg["costs"]["spread"]["series"][name]
    return E.SpreadModel(prof, man, series, fx=name in ("EURUSD", "GBPUSD", "USDJPY"), stat=stat, mult=mult)


def pd_lookup(pw_levels: list[E.Level]) -> dict:
    out = {}
    for L in pw_levels:
        out[int(L.seg_t[0])] = (L.meta["range_hi"], L.meta["range_lo"])
    return out


def pd_state(level: float, t: int, look: dict, band: float = 0.05) -> str:
    ws = int(E.week_start(t))
    if ws not in look:
        return "unknown"
    hi, lo = look[ws]
    eq, b = (hi + lo) / 2, band * (hi - lo)
    if level > eq + b:
        return "premium"
    if level < eq - b:
        return "discount"
    return "neutral"


# ----------------------------------------------------------------------------- descriptive context (4.7, m-6, A-19)
class Context:
    """Regime and event-study inputs, all from data strictly before the reclaim close."""

    def __init__(self, m1: E.Bars, h1: E.Bars, atr_h1: np.ndarray):
        self.m1 = m1
        # D1 = UTC day; ATR14 D1 percentile of the last completed day within the trailing 252 completed days
        d1 = E.resample(m1, 1440)
        a = E.atr14(d1)
        s = pd.Series(a)
        self.d1_tc = d1.tc
        self.d1_pct = s.rolling(252, min_periods=252).apply(lambda x: (x[:-1] < x[-1]).mean() * 100 +
                                                            (x[:-1] == x[-1]).mean() * 50, raw=True).to_numpy()
        # weekly closes (Mon 00:00 UTC weeks)
        wk = E.week_start(m1.t)
        last = np.r_[np.flatnonzero(np.diff(wk)), len(wk) - 1]
        self.wk_keys = wk[last]
        self.wk_close = m1.c[last]
        # event study: forward k-hour move from each H1 close in H1-ATR units, baseline = prior calendar years'
        # mean for the same UTC hour-of-week (m-7)
        self.h1, self.atr_h1 = h1, atr_h1
        tc = h1.tc
        how = ((tc // E.NS_H) + 72) % 168
        yr = pd.DatetimeIndex(tc.astype("datetime64[ns]")).year.to_numpy()
        self.base = {}
        for k in EV_H:
            fwd = (self.px_at(tc + k * E.NS_H) - h1.c) / atr_h1
            df = pd.DataFrame({"y": yr, "how": how, "f": fwd}).dropna()
            g = df.groupby(["y", "how"]).f.agg(["sum", "count"]).unstack("how").fillna(0)
            cs = g.cumsum().shift(1)        # prior calendar years only
            mean = cs["sum"] / cs["count"].replace(0, np.nan)
            self.base[k] = mean

    def px_at(self, ns: np.ndarray) -> np.ndarray:
        """Last M1 close at or before time ns (NaN beyond the data)."""
        i = np.searchsorted(self.m1.t, ns, "left") - 1
        out = self.m1.c[np.clip(i, 0, None)].astype(float)
        out[(i < 0) | (ns > self.m1.t[-1] + E.NS_MIN)] = np.nan
        return out

    def features(self, t: int, close: float, long: bool) -> dict:
        out = {}
        j = np.searchsorted(self.d1_tc, t, "right") - 1
        out["vol_pct"] = float(self.d1_pct[j]) if j >= 0 else np.nan
        w = int(E.week_start(t))
        i = np.searchsorted(self.wk_keys, w, "left")     # index of current week; need weeks i-1 and i-5
        if i >= 5 and self.wk_keys[i - 1] == w - 7 * E.NS_D:
            d = self.wk_close[i - 1] - self.wk_close[i - 5]
            out["trend"] = "with" if (d > 0 and long) or (d < 0 and not long) else "against"   # tie = against
        else:
            out["trend"] = "unknown"
        h = np.searchsorted(self.h1.tc, t, "right") - 1
        atr = self.atr_h1[h] if h >= 0 else np.nan
        yr = pd.Timestamp(t, tz="UTC").year
        how = ((t // E.NS_H) + 72) % 168
        sgn = 1.0 if long else -1.0
        for k in EV_H:
            p = self.px_at(np.array([t + k * E.NS_H]))[0]
            mv = (p - close) / atr
            b = self.base[k]
            base = b.loc[yr, how] if yr in b.index else np.nan
            out[f"ev{k}"] = float(sgn * (mv - base)) if np.isfinite(base) else np.nan
        return out


def build_signals(levels, bars, atr_tf, m1: E.Bars, inst, look, spr, ctx: Context | None = None) -> tuple[list[dict], dict]:
    sigs, counts = [], {}
    for L in levels:
        ev = E.scan_level(L, bars, atr_tf, inst)
        st = ev["status"] if ev else "not_active"
        counts[st] = counts.get(st, 0) + 1
        if not ev or ev["status"] != "reclaim":
            continue
        if E.in_weekend_window(ev["sweep_t"], inst):
            counts["weekend_window_sweep"] = counts.get("weekend_window_sweep", 0) + 1
            continue
        k = int(np.searchsorted(m1.t, ev["sweep_t"], "left"))
        gap_sweep = bool(k > 0 and k < len(m1.t) and m1.t[k] - m1.t[k - 1] >= 30 * E.NS_MIN and
                         ((m1.o[k] >= ev["level"]) if L.side == "high" else (m1.o[k] <= ev["level"])))
        state = pd_state(ev["level"], ev["reclaim_close_t"] - 1, look)
        aligned = (L.side == "low" and state == "discount") or (L.side == "high" and state == "premium")
        _, ext = spr.at(np.array([ev["reclaim_close_t"] - 1]), np.array([ev["close"]]))
        ev.update(pd_state=state, aligned=aligned, gap_sweep=gap_sweep, spread_extrapolated=bool(ext[0]),
                  sid=f"{L.lid}|{ev['sweep_t']}")
        if ctx is not None:
            ev.update(ctx.features(ev["reclaim_close_t"], ev["close"], L.side == "low"))
        sigs.append(ev)
    # v0.6 M-2: same source, same reclaim candle -> earliest sweep trades, others signalled_not_executed
    by = {}
    for s in sigs:
        by.setdefault(s["reclaim_close_t"], []).append(s)
    for grp in by.values():
        grp.sort(key=lambda x: x["sweep_t"])
        for s in grp[1:]:
            s["tie_loser"] = True
    return sigs, counts


def instrument_inputs(name: str, cfg: dict):
    inst = E.instruments_from_config(cfg)[name]
    m1df = load_m1(name)
    m1 = E.m1_arrays(m1df)
    spr = spread_model(cfg, name)
    spr_m1, ext_m1 = spr.at(m1.t, m1.o)
    gaps = E.gap_intervals(m1)
    bars = {tf: E.resample(m1, E.TF_MIN[tf]) for tf in TFS}
    atrs = {tf: E.atr14(bars[tf]) for tf in TFS}
    return inst, m1, spr, spr_m1, gaps, bars, atrs


def cells_for(source: str) -> list[str]:
    return ["none"] if source in ("pw", "pw_stale", "pw_rand") else ["none", "aligned"]


# ----------------------------------------------------------------------------- cost scenarios (3.4, A-14, M-3)
def scenarios(name: str, cfg: dict, inst: E.Instrument, m1: E.Bars, spr, spr_m1: np.ndarray) -> dict:
    """name -> (spr_m1, spread_at, inst, slip_mult, buffer_atr). All re-price the primary fixed trade list."""
    def scaled(k):
        return lambda t, b: (spr.at(t, b)[0] * k, np.zeros(len(t), bool))

    out = {}
    for k in (0.5, 1.5, 2.0, 3.0):
        out[f"spread_x{k:g}"] = (spr_m1 * k, scaled(k), inst, 1.0, 0.10)
    p90 = spread_model(cfg, name, stat="p90")
    out["spread_p90"] = (p90.at(m1.t, m1.o)[0], p90.at, inst, 1.0, 0.10)
    out["slip_x2"] = (spr_m1, spr.at, inst, 2.0, 0.10)
    out["slip_x4"] = (spr_m1, spr.at, inst, 4.0, 0.10)
    out["worst_spread_x2_slip_x2"] = (spr_m1 * 2, scaled(2.0), inst, 2.0, 0.10)
    out["buffer_0.05"] = (spr_m1, spr.at, inst, 1.0, 0.05)
    out["buffer_0.2"] = (spr_m1, spr.at, inst, 1.0, 0.20)
    # H001 cost floors exactly as frozen (4.8): constant spread and absolute slippage in pips
    h1c = yaml.safe_load(open(ROOT / "config/h001.yaml"))["h001"]
    h1, pip = h1c["costs"], h1c["pip_size"][name]
    fl = h1["spread_floor_pips"][name] * pip
    inst_h1 = dataclasses.replace(inst, pip=pip, slip_pips=h1["slippage_pips_per_side"][name], slip_bp=None)
    out["h001_floor"] = (np.full(len(m1.t), fl), lambda t, b, fl=fl: (np.full(len(t), fl), np.zeros(len(t), bool)),
                         inst_h1, 1.0, 0.10)
    if name == "BTCUSD":
        out["btc_flat_20usd"] = (np.full(len(m1.t), 20.0), lambda t, b: (np.full(len(t), 20.0), np.zeros(len(t), bool)),
                                 inst, 1.0, 0.10)
        for bp in (2, 5, 10):
            out[f"btc_{bp}bp"] = (bp * 1e-4 * m1.o, lambda t, b, bp=bp: (bp * 1e-4 * np.asarray(b, float), np.zeros(len(t), bool)),
                                  inst, 1.0, 0.10)
    return out


# ----------------------------------------------------------------------------- placebos (4.5 + v0.6 M-16)
def random_offset_levels(pw: list[E.Level], rng: np.random.Generator) -> list[E.Level]:
    out = []
    for L in pw:
        hi, lo = L.meta["range_hi"], L.meta["range_lo"]
        u = rng.uniform(0.1, 0.5)
        v = hi + u * (hi - lo) if L.side == "high" else lo - u * (hi - lo)
        out.append(dataclasses.replace(L, source="pw_rand", lid=L.lid.replace("pw:", "pwr:"), seg_v=np.array([v])))
    return out


def stale_levels(pw: list[E.Level]) -> list[E.Level]:
    by = {(int(L.seg_t[0]), L.side): L for L in pw}
    out = []
    for L in pw:
        P = by.get((int(L.seg_t[0]) - 7 * E.NS_D, L.side))
        if P is not None:
            out.append(dataclasses.replace(L, source="pw_stale", lid=L.lid.replace("pw:", "pws:"), seg_v=P.seg_v.copy()))
    return out


def tag(df: pd.DataFrame, name: str, tf: str, filt: str) -> pd.DataFrame:
    df["instrument"], df["tf"], df["filter"] = name, tf, filt
    return df


def period_of(t: pd.Series) -> np.ndarray:
    return np.where(t < HIST_END, "historical", np.where(t < EXPOSED_END, "exposed", "after_exposed"))


def run_instrument(name: str, cfg: dict, out: Path, log=print, placebo_draws: int | None = None) -> pd.DataFrame:
    inst, m1, spr, spr_m1, gaps, bars, atrs = instrument_inputs(name, cfg)
    ctx = Context(m1, bars["H1"], atrs["H1"])
    pw = E.period_levels(m1, "pw")
    pm = E.period_levels(m1, "pm")
    eq = E.eq_clusters(bars["H1"], inst)
    eq_u = E.eq_clusters(bars["H1"], inst, unequal_placebo=True)
    for L in eq_u:
        L.source = "eq_unequal"
    look = pd_lookup(pw)
    sources = {"pw": pw, "pm": pm, "eq": eq, "pw_stale": stale_levels(pw), "eq_unequal": eq_u}
    all_rows, sig_counts, all_sigs = [], [], []
    cell_sigs = {}
    for src, levels in sources.items():
        for tf in TFS:
            sigs, counts = build_signals(levels, bars[tf], atrs[tf], m1, inst, look, spr, ctx)
            sig_counts.append({"instrument": name, "source": src, "tf": tf, **counts, "signals": len(sigs)})
            if sigs:
                all_sigs.append(tag(pd.DataFrame(sigs), name, tf, "all"))
            for filt in cells_for(src):
                use = sigs if filt == "none" else [s for s in sigs if s["aligned"]]
                df = tag(simulate_cell(use, m1, spr_m1, spr.at, inst, gaps), name, tf, filt)
                all_rows.append(df)
                cell_sigs[(src, tf, filt)] = use
                ex = (df.status == "executed").sum() if len(df) else 0
                log(f"{name} {src} {tf} {filt}: signals {len(use)}, executed {ex}")
    trades = pd.concat(all_rows, ignore_index=True)
    trades["period"] = period_of(trades.reclaim_close_t)
    trades["binance_proxy"] = (name == "BTCUSD") & (trades.sweep_t < BTC_EXNESS_FROM)
    out.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(out / f"{name}_trades.parquet")
    pd.concat(all_sigs, ignore_index=True).to_parquet(out / f"{name}_signals.parquet")
    pd.DataFrame(sig_counts).to_csv(out / f"{name}_signal_counts.csv", index=False)
    pd.DataFrame(gaps, columns=["start", "end"]).to_parquet(out / f"{name}_gaps.parquet")

    # fixed-list sensitivities (M-3): same executed trades, re-priced
    sc = scenarios(name, cfg, inst, m1, spr, spr_m1)
    sens = []
    for (src, tf, filt), use in cell_sigs.items():
        if src not in ("pw", "eq", "pm"):
            continue
        d = trades[(trades.source == src) & (trades.tf == tf) & (trades["filter"] == filt) & (trades.status == "executed")]
        fixed = set(d.sid)
        if not fixed:
            continue
        for sname, (sm1, sat, sinst, smult, sbuf) in sc.items():
            df = simulate_cell(use, m1, sm1, sat, sinst, gaps, buffer_atr=sbuf, slip_mult=smult, fixed_list=fixed)
            df = tag(df, name, tf, filt)
            df["scenario"] = sname
            sens.append(df[[c for c in ("sid", "source", "side", "status", "r", "R", "entry", "nights", "t_entry",
                                        "reclaim_close_t", "instrument", "tf", "filter", "scenario") if c in df]])
        log(f"{name} {src} {tf} {filt}: sensitivities done")
    sens = pd.concat(sens, ignore_index=True)
    sens["period"] = period_of(sens.reclaim_close_t)
    sens.to_parquet(out / f"{name}_sensitivities.parquet")

    # random-offset PW placebo, 200 draws (4.5, M-16)
    pc = cfg["placebo"]["random_offset"]
    n_draws = pc["draws"] if placebo_draws is None else placebo_draws
    rng = np.random.default_rng(pc["seed"])
    rows = []
    for d in range(n_draws):
        lv = random_offset_levels(pw, rng)
        for tf in TFS:
            sigs, _ = build_signals(lv, bars[tf], atrs[tf], m1, inst, look, spr)
            df = simulate_cell(sigs, m1, spr_m1, spr.at, inst, gaps)
            if len(df) and "r" in df:
                x = df[df.status == "executed"]
                per = period_of(x.reclaim_close_t)
                for p in ("historical", "exposed"):
                    r = x.r[per == p]
                    rows.append({"instrument": name, "tf": tf, "draw": d, "period": p, "n": len(r), "sum_r": r.sum(),
                                 "mean_r": r.mean() if len(r) else np.nan})
        if d % 20 == 19:
            log(f"{name} placebo draw {d + 1}/{n_draws}")
    pd.DataFrame(rows).to_parquet(out / f"{name}_placebo_random.parquet")
    return trades
