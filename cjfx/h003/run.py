"""H003 runner (spec v0.2). python -m cjfx.h003.run  -> results/h003/final/"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from cjfx.h003 import engine as E

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/h003/final"
EVAL_END = pd.Timestamp("2023-12-31")
N_TRIALS = 13_884
BAR_T = 2.64
SEED = 20261126
INSTR = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "NAS100", "BTCUSD"]


def load_days(name: str) -> pd.DataFrame:
    cache = ROOT / f"data/h003/{name}_daily.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    if name == "BTCUSD":
        files = sorted((ROOT / "data/exness_m1/BTCUSDm").glob("*.parquet"))
        m1 = pd.concat([pd.read_parquet(f) for f in files]).sort_index()
    else:
        m1 = pd.read_parquet(ROOT / f"data/m1/{name}_M1_h003.parquet")
    m1 = m1[~m1.index.duplicated(keep="last")]
    d = E.daily_bars(m1, btc=name == "BTCUSD")
    cache.parent.mkdir(parents=True, exist_ok=True)
    d.to_parquet(cache)
    return d


def spreads(name: str, days: pd.DataFrame, mult=1.0) -> np.ndarray:
    base = ROOT / f"results/h003/spreads/{E.SERIES[name]}"
    return E.spread_frac(days, pd.read_csv(base / "spread_profiles.csv"), pd.read_csv(base / "cost_inputs.csv"), mult)


def swap_m(name, which):
    if name == "BTCUSD":
        return {"primary": E.SWAP_M["btc_primary"], "stress": E.SWAP_M["btc_stress"]}.get(which, which)
    return {"primary": E.SWAP_M["primary"], "stress": E.SWAP_M["stress"]}.get(which, which)


def simulate(name, days, spr, S=None, p=None, m="primary", spread_mult=1.0, slip_mult=1.0):
    p = p or E.params_for(name)
    S = E.signal(days["close"], p) if S is None else S
    w = E.target_weights(days["close"], p, S)
    h = E.held_weights(w, S, p.band)
    c = E.Costs(spread=spr, slip_abs=E.SLIP[name], swap_m=swap_m(name, m), btc=name == "BTCUSD",
                spread_mult=spread_mult, slip_mult=slip_mult)
    r = E.daily_returns(days, h, c)
    r["S"] = S.shift(1).to_numpy()      # signal in force during the day (decided at prior close)
    return r


def live(r: pd.DataFrame) -> pd.DataFrame:
    """Days from the first day with a position decided (post warm-up)."""
    first = r.index[np.isfinite(r["S"].to_numpy())]
    return r.loc[first[0]:] if len(first) else r.iloc[0:0]


def summ(x: pd.Series, ann: int) -> dict:
    x = x.dropna()
    t, se = E.nw_t(x.to_numpy(), 21)
    eq = (1 + x).cumprod()
    dd = eq / eq.cummax() - 1
    under = (eq < eq.cummax()).astype(int)
    runs = under.groupby((under != under.shift()).cumsum()).sum().max() if len(x) else 0
    return {"days": len(x), "years": round(len(x) / ann, 1), "mean_bp_day": x.mean() * 1e4,
            "ann_ret": x.mean() * ann, "ann_vol": x.std() * np.sqrt(ann),
            "sharpe": x.mean() / x.std() * np.sqrt(ann) if x.std() > 0 else np.nan, "nw_t": t,
            "max_dd": dd.min(), "longest_underwater_days": int(runs)}


def run_instrument(name: str, rng: np.random.Generator, log=print) -> tuple[dict, dict]:
    days = load_days(name)
    p = E.params_for(name)
    ann = p.ann
    spr = spreads(name, days)
    base = simulate(name, days, spr)
    L = live(base)
    ev, ex = L[L.index <= EVAL_END], L[L.index > EVAL_END]
    res = {"instrument": name, "eval_start": str(ev.index[0].date()), "eval_end": str(ev.index[-1].date())}
    s = summ(ev["net"], ann)
    res.update({f"net_{k}": v for k, v in s.items()})
    res.update({f"gross_{k}": v for k, v in summ(ev["gross"], ann).items() if k in ("ann_ret", "sharpe", "nw_t")})
    res.update({f"exswap_{k}": v for k, v in summ(ev["net_ex_swap"], ann).items() if k in ("ann_ret", "sharpe", "nw_t")})
    res["cost_tc_ann"] = ev["tcost"].mean() * ann
    res["cost_swap_ann"] = ev["swap"].mean() * ann
    res["trades_per_year"] = ev["trade"].sum() / (len(ev) / ann)
    res["sign_flips_per_year"] = (np.sign(ev["S"]).diff().fillna(0) != 0).sum() / (len(ev) / ann)
    res["exec_fallback_share"] = float(days.loc[ev.index, "exec_fallback"].mean())
    res["pre_archive_share"] = float((ev.index < pd.Timestamp(
        pd.read_csv(ROOT / f"results/h003/spreads/{E.SERIES[name]}/cost_inputs.csv")["month"].min() + "-01")).mean())
    # 1. bootstrap t
    x = ev["net"].to_numpy()
    bm = E.stationary_bootstrap_means_fast(x, 10_000, 21, rng)
    res["boot_t"] = x.mean() / bm.std()
    res["c1_t"] = bool(x.mean() > 0 and res["net_nw_t"] >= BAR_T and res["boot_t"] >= BAR_T)
    # 2. positive years
    yr = ev["net"].groupby(ev.index.year).apply(lambda v: (1 + v).prod() - 1)
    need = int(np.ceil(0.6 * len(yr)))
    res["years_pos"], res["years_n"], res["years_need"] = int((yr > 0).sum()), len(yr), need
    res["c2_years"] = bool(res["years_pos"] >= need)
    # 3a. sign-scramble placebo
    S_full = E.signal(days["close"], p)
    pm = []
    for _ in range(2000):
        Sp = E.block_sign_placebo(S_full, 21, rng)
        rp = simulate(name, days, spr, S=Sp)
        pm.append(rp.loc[ev.index, "net"].mean())
    pm = np.array(pm)
    res["placebo_p"] = float((pm >= x.mean()).mean())
    res["placebo_mean_bp"] = pm.mean() * 1e4
    # 3b. historical-mean rule (Huang et al. 2020)
    lr = np.log(days["close"]).diff()
    S_hm = np.sign(lr.expanding(min_periods=p.warmup).mean())
    S_hm.iloc[: p.warmup] = np.nan
    rh = simulate(name, days, spr, S=S_hm)
    diff = ev["net"] - rh.loc[ev.index, "net"]
    res["histmean_sharpe"] = summ(rh.loc[ev.index, "net"], ann)["sharpe"]
    res["vs_histmean_t"] = E.nw_t(diff.to_numpy(), 21)[0]
    res["c3_beats"] = bool(res["placebo_p"] < 0.05 and res["vs_histmean_t"] > 1.645)
    # 4. stress
    st = simulate(name, days, spr, m="stress", spread_mult=1.5, slip_mult=2.0).loc[ev.index, "net"]
    res["stress_ann_ret"] = st.mean() * ann
    res["c4_stress"] = bool(st.mean() > 0)
    # 5. long/short or beats vol-scaled buy-and-hold
    res["long_contrib_ann"] = ev["net"].where(ev["w_new"] > 0, 0).mean() * ann
    res["short_contrib_ann"] = ev["net"].where(ev["w_new"] < 0, 0).mean() * ann
    S_bh = pd.Series(1.0, index=days.index)
    S_bh.iloc[: p.warmup] = np.nan
    rb = simulate(name, days, spr, S=S_bh)
    res["buyhold_sharpe"] = summ(rb.loc[ev.index, "net"], ann)["sharpe"]
    res["vs_buyhold_t"] = E.nw_t((ev["net"] - rb.loc[ev.index, "net"]).to_numpy(), 21)[0]
    res["c5_not_drift"] = bool((res["long_contrib_ann"] >= 0 and res["short_contrib_ann"] >= 0) or res["vs_buyhold_t"] > 1.645)
    # 6. deflated Sharpe
    res["dsr"] = E.deflated_sharpe(x, N_TRIALS)
    res["c6_dsr"] = bool(res["dsr"] > 0.95)
    # 7. exposed
    res["exposed_ann_ret"] = ex["net"].mean() * ann if len(ex) else np.nan
    res["exposed_sharpe"] = summ(ex["net"], ann)["sharpe"] if len(ex) > 20 else np.nan
    res["c7_exposed"] = bool(len(ex) and ex["net"].mean() >= 0)
    res["PASS"] = all(res[k] for k in ("c1_t", "c2_years", "c3_beats", "c4_stress", "c5_not_drift", "c6_dsr", "c7_exposed"))
    # swap sensitivities (re-pricing same positions)
    for mm in (0.0, 0.02, 0.04, 0.06):
        res[f"ann_ret_swap_{int(mm*100)}pct"] = simulate(name, days, spr, m=mm).loc[ev.index, "net"].mean() * ann
    be = ev["net_ex_swap"].mean() / max((ev["swap"] / swap_m(name, "primary")).mean(), 1e-12)
    res["break_even_swap_m"] = be

    # ---------------- diagnostics (outside family)
    diag = {"instrument": name}
    for Lb in p.lookbacks:
        pp = E.params_for(name)
        pp.lookbacks = (Lb,)
        r1 = simulate(name, days, spr, p=pp).loc[ev.index, "net"]
        sm = summ(r1, ann)
        diag[f"L{Lb}_sharpe"], diag[f"L{Lb}_t"] = sm["sharpe"], sm["nw_t"]
    pn = E.params_for(name)
    pn.vol_scale = False
    sm = summ(simulate(name, days, spr, p=pn).loc[ev.index, "net"], ann)
    diag["novolscale_sharpe"], diag["novolscale_t"] = sm["sharpe"], sm["nw_t"]
    for lab, a, b in (("2000_2010", "2000-01-01", "2010-12-31"), ("2011_2023", "2011-01-01", "2023-12-31"),
                      ("2024_2026", "2024-01-01", "2026-12-31")):
        seg = L.loc[a:b, "net"]
        if len(seg) > 250:
            sm = summ(seg, ann)
            diag[f"{lab}_sharpe"], diag[f"{lab}_t"], diag[f"{lab}_ann_ret"] = sm["sharpe"], sm["nw_t"], sm["ann_ret"]
    # volatility-expansion split (regime known at the signal close)
    lrs = np.log(days["close"]).diff()
    ratio = (lrs.rolling(5).std() / lrs.rolling(60).std()).shift(1).reindex(ev.index)
    for lab, mask in (("expanding", ratio > 1.25), ("contracting", ratio < 0.8),
                      ("neutral", (ratio >= 0.8) & (ratio <= 1.25))):
        seg = ev.loc[mask.fillna(False), "net"]
        diag[f"vol_{lab}_days"] = len(seg)
        diag[f"vol_{lab}_ann_ret"] = seg.mean() * ann
        diag[f"vol_{lab}_t"] = E.nw_t(seg.to_numpy(), 5)[0] if len(seg) > 30 else np.nan
    # squeeze breakout: 20d close-range in lowest quintile of past 252 days, then close breaks the range
    C = days["close"]
    hi, lo = C.rolling(20).max().shift(1), C.rolling(20).min().shift(1)
    rngr = (hi - lo) / C.shift(1)
    q20 = rngr.rolling(252).quantile(0.2)
    sq = rngr <= q20
    direction = np.where(sq & (C > hi), 1, np.where(sq & (C < lo), -1, 0))
    sig_d = pd.Series(direction, index=days.index)
    fwd = (np.log(C.shift(-5)) - np.log(days["exec_px"].shift(-1)))      # enter next 03:00 NY, hold 5 days
    vol_d = E.sigma_hat(C, p) / np.sqrt(ann)
    z = (sig_d * fwd / vol_d)[(sig_d != 0) & (days.index <= EVAL_END)].dropna()
    diag["squeeze_events"] = len(z)
    diag["squeeze_fwd5_mean_sigma"] = z.mean() if len(z) else np.nan
    diag["squeeze_fwd5_t"] = E.nw_t(z.to_numpy(), 1)[0] if len(z) > 30 else np.nan
    log(f"{name}: net SR {res['net_sharpe']:.2f} t {res['net_nw_t']:.2f} boot_t {res['boot_t']:.2f} PASS {res['PASS']}")
    L[["gross", "tcost", "swap", "net", "w_new", "S"]].to_parquet(OUT / f"daily_{name}.parquet")
    return res, diag


def main(names=INSTR):
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    rows, diags = [], []
    for n in names:
        r, d = run_instrument(n, rng)
        rows.append(r)
        diags.append(d)
        pd.DataFrame(rows).to_csv(OUT / "family_6.csv", index=False)
        pd.DataFrame(diags).to_csv(OUT / "diagnostics.csv", index=False)
    # descriptive equal-risk portfolio (cannot qualify anything)
    ser = []
    for n in names:
        d = pd.read_parquet(OUT / f"daily_{n}.parquet")["net"]
        d.index = pd.to_datetime(d.index)
        if n == "BTCUSD":   # roll weekend returns into the next weekday
            d = (1 + d).groupby(d.index + pd.offsets.BDay(0)).prod() - 1
        ser.append(d.rename(n))
    pf = pd.concat(ser, axis=1)
    pf = pf[pf.index.dayofweek < 5]
    port = pf.mean(axis=1, skipna=True)
    out = {}
    for lab, a, b in (("eval_to_2023", "2000-01-01", "2023-12-31"), ("2000_2010", "2000-01-01", "2010-12-31"),
                      ("2011_2023", "2011-01-01", "2023-12-31"), ("2024_2026", "2024-01-01", "2026-12-31")):
        out[lab] = summ(port.loc[a:b], 261)
    json.dump(out, open(OUT / "portfolio_descriptive.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main(sys.argv[1:] or INSTR)
