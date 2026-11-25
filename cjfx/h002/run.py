"""H002 runner: signals and trades per instrument and cell (spec v0.6)."""
from __future__ import annotations

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


def build_signals(levels, bars, atr_tf, m1: E.Bars, inst, look, spr) -> tuple[list[dict], dict]:
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
    return ["none"] if source == "pw" else ["none", "aligned"]


def run_instrument(name: str, cfg: dict, out: Path, log=print, placebo_draws: int = 0) -> pd.DataFrame:
    inst, m1, spr, spr_m1, gaps, bars, atrs = instrument_inputs(name, cfg)
    pw = E.period_levels(m1, "pw")
    pm = E.period_levels(m1, "pm")
    eq = E.eq_clusters(bars["H1"], inst)
    look = pd_lookup(pw)
    sources = {"pw": pw, "pm": pm, "eq": eq}
    all_rows, sig_counts = [], []
    for src, levels in sources.items():
        for tf in TFS:
            sigs, counts = build_signals(levels, bars[tf], atrs[tf], m1, inst, look, spr)
            sig_counts.append({"instrument": name, "source": src, "tf": tf, **counts, "signals": len(sigs)})
            for filt in cells_for(src):
                use = sigs if filt == "none" else [s for s in sigs if s["aligned"]]
                df = simulate_cell(use, m1, spr_m1, spr.at, inst, gaps)
                df["instrument"], df["tf"], df["filter"] = name, tf, filt
                all_rows.append(df)
                ex = (df.status == "executed").sum() if len(df) else 0
                log(f"{name} {src} {tf} {filt}: signals {len(use)}, executed {ex}")
    trades = pd.concat(all_rows, ignore_index=True)
    trades["period"] = np.where(trades.reclaim_close_t < HIST_END, "historical",
                                np.where(trades.reclaim_close_t < EXPOSED_END, "exposed", "after_exposed"))
    out.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(out / f"{name}_trades.parquet")
    pd.DataFrame(sig_counts).to_csv(out / f"{name}_signal_counts.csv", index=False)
    pd.DataFrame(gaps, columns=["start", "end"]).to_parquet(out / f"{name}_gaps.parquet")
    return trades
