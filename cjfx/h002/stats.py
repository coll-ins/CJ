"""H002 statistics (spec 4.4, 4.5, 4.7, 7 and v0.6 M-13, M-14, M-15, m-10, m-16)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

from . import engine as E
from .run import HIST_END

INSTRUMENTS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "NAS100")
FAMILY = [(s, tf, f) for s, fl in (("pw", ("none",)), ("eq", ("none", "aligned"))) for tf in ("M5", "M15", "H1")
          for f in fl]
DESCRIPTIVE = [("pm", tf, f) for tf in ("M5", "M15", "H1") for f in ("none", "aligned")]
UNEQUAL = [("eq_unequal", tf, f) for tf in ("M5", "M15", "H1") for f in ("none", "aligned")]
STALE = [("pw_stale", tf, "none") for tf in ("M5", "M15", "H1")]
RISK = 0.005
BTC_FROM = pd.Timestamp("2017-08-17", tz="UTC").value
WEEK0 = pd.Timestamp("2011-01-03", tz="UTC").value


def stationary_index(n_weeks: int, draws: int, mean_block: float, seed: int) -> np.ndarray:
    """Politis-Romano stationary bootstrap of week positions (circular), one index for all cells (m-15)."""
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_block
    starts = rng.integers(0, n_weeks, size=(draws, n_weeks))
    new = rng.random((draws, n_weeks)) < p
    idx = np.empty((draws, n_weeks), np.int32)
    idx[:, 0] = starts[:, 0]
    for j in range(1, n_weeks):
        idx[:, j] = np.where(new[:, j], starts[:, j], (idx[:, j - 1] + 1) % n_weeks)
    return idx


def week_counts(idx: np.ndarray, n_weeks: int) -> np.ndarray:
    K = np.empty(idx.shape, np.float32)
    for b in range(idx.shape[0]):
        K[b] = np.bincount(idx[b], minlength=n_weeks)
    return K


def max_drawdown(r: np.ndarray) -> tuple[float, float]:
    if not len(r):
        return np.nan, np.nan
    cum = np.cumsum(r)
    dd_r = float(np.max(np.maximum.accumulate(np.r_[0, cum])[1:] - cum))
    eq = np.cumprod(1 + RISK * r)
    peak = np.maximum.accumulate(np.r_[1.0, eq])[1:]
    dd_pct = float(np.max(1 - eq / peak) * 100)
    return dd_r, dd_pct


def daily_sharpe(x: pd.DataFrame, btc: bool) -> float:
    if len(x) < 2:
        return np.nan
    d = pd.to_datetime(x.t_exit, utc=True).dt.normalize()
    pnl = (RISK * x.r).groupby(d).sum()
    days = pd.date_range(pnl.index.min(), pnl.index.max(), freq="D" if btc else "B", tz="UTC")
    s = pnl.reindex(days, fill_value=0.0)
    ann = 365 if btc else 252
    return float(s.mean() / s.std() * np.sqrt(ann)) if s.std() > 0 else np.nan


def deflated_sharpe(sr: float, T: int, skew: float, kurt: float, var_sr: float, trials: int) -> float:
    """Bailey & Lopez de Prado (2014). kurt = raw (non-excess) kurtosis of per-trade R."""
    g = 0.5772156649
    sr0 = np.sqrt(var_sr) * ((1 - g) * st.norm.ppf(1 - 1 / trials) + g * st.norm.ppf(1 - 1 / (trials * np.e)))
    den = np.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr ** 2, 1e-12))
    return float(st.norm.cdf((sr - sr0) * np.sqrt(T - 1) / den))


def romano_wolf(t_obs: np.ndarray, t_boot: np.ndarray) -> np.ndarray:
    """Two-sided stepdown adjusted p-values. t_boot: (B, C) centred, studentised bootstrap stats."""
    a = np.abs(t_obs)
    ab = np.abs(t_boot)
    order = np.argsort(-a)
    p = np.empty(len(a))
    prev = 0.0
    for k, c in enumerate(order):
        rest = order[k:]
        mx = np.nanmax(ab[:, rest], axis=1)
        pv = max(prev, float(np.mean(mx >= a[c])))
        p[c] = pv
        prev = pv
    return p


def cell_key(src, tf, f):
    return f"{src}|{tf}|{f}"


class Study:
    def __init__(self, res: Path, cfg: dict):
        self.res, self.cfg = res, cfg
        self.trades = {n: pd.read_parquet(res / f"{n}_trades.parquet") for n in INSTRUMENTS if (res / f"{n}_trades.parquet").exists()}
        self.sens = {n: pd.read_parquet(res / f"{n}_sensitivities.parquet") for n in self.trades}
        self.plac = {n: pd.read_parquet(res / f"{n}_placebo_random.parquet") for n in self.trades}
        self.sigs = {n: pd.read_parquet(res / f"{n}_signals.parquet") for n in self.trades}

    # ------------------------------------------------------------------ helpers
    def executed(self, n, src, tf, f, period="historical"):
        t = self.trades[n]
        x = t[(t.source == src) & (t.tf == tf) & (t["filter"] == f) & (t.status == "executed")]
        if period:
            x = x[x.period == period]
        if n == "BTCUSD" and period == "historical":
            x = x[x.reclaim_close_t >= BTC_FROM]
        return x.sort_values("t_exit")

    def all_rows(self, n, src, tf, f, period="historical"):
        t = self.trades[n]
        x = t[(t.source == src) & (t.tf == tf) & (t["filter"] == f)]
        return x[x.period == period] if period else x

    # ------------------------------------------------------------------ bootstrap over weeks (4.4)
    def bootstrap(self, cells: list[tuple]) -> dict:
        bs = self.cfg["stats"]["bootstrap"]
        wk_end = int(E.week_start(HIST_END - 1))
        W = (wk_end - WEEK0) // (7 * E.NS_D) + 1
        S = np.zeros((W, len(cells)))
        N = np.zeros((W, len(cells)))
        for c, (n, src, tf, f) in enumerate(cells):
            x = self.executed(n, src, tf, f)
            w = ((E.week_start(x.t_entry.to_numpy(np.int64)) - WEEK0) // (7 * E.NS_D)).astype(int)
            np.add.at(S[:, c], w, x.r.to_numpy())
            np.add.at(N[:, c], w, 1)
        idx = stationary_index(W, bs["draws"], bs["mean_block_weeks"], bs["seed"])
        K = week_counts(idx, W)
        bsum, bn = K @ S, K @ N
        with np.errstate(invalid="ignore", divide="ignore"):
            bmean = bsum / bn
        mean = S.sum(0) / np.where(N.sum(0) > 0, N.sum(0), np.nan)
        se = np.nanstd(bmean, axis=0, ddof=1)
        return {"cells": cells, "mean": mean, "se": se, "boot": bmean, "W": W, "K": K, "S": S, "N": N}

    # ------------------------------------------------------------------ per-cell report
    def metrics(self, n, src, tf, f, period="historical") -> dict:
        x = self.executed(n, src, tf, f, period)
        rows = self.all_rows(n, src, tf, f, period)
        r = x.r.to_numpy()
        btc = n == "BTCUSD"
        out = {"instrument": n, "source": src, "tf": tf, "filter": f, "period": period,
               "eligible": len(rows), "executed": len(r)}
        for s_, k in rows.status.value_counts().items():
            if s_ != "executed":
                out[f"skip_{s_}"] = int(k)
        ds = int((rows.status == "data_gap").sum())
        out["unscorable_share"] = ds / max(ds + len(r), 1)
        if not len(r):
            return out
        wins, losses = r[r > 0].sum(), -r[r < 0].sum()
        out.update(expectancy=r.mean(), sd=r.std(ddof=1) if len(r) > 1 else np.nan, win_rate=(r > 0).mean(),
                   target_rate=(x.outcome == "target").mean(), profit_factor=wins / losses if losses > 0 else np.inf,
                   naive_t=r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 1 else np.nan,
                   hold_h=x.hold_h.mean(), nights_share=(x.nights > 0).mean(),
                   sr_trade=r.mean() / r.std(ddof=1) if len(r) > 1 else np.nan,
                   sr_daily_ann=daily_sharpe(x, btc), skew=st.skew(r) if len(r) > 2 else np.nan,
                   kurt=st.kurtosis(r, fisher=False) if len(r) > 3 else np.nan)
        out["maxdd_r"], out["maxdd_pct"] = max_drawdown(r)
        lg, sh = x[x.side == "low"].r, x[x.side == "high"].r
        out.update(long_n=len(lg), long_e=lg.mean() if len(lg) else np.nan, short_n=len(sh),
                   short_e=sh.mean() if len(sh) else np.nan)
        if period == "historical":
            yrs = range(2018, 2024) if btc else range(2011, 2024)
            y = pd.to_datetime(x.t_entry, utc=True).dt.year
            by = x.r.groupby(y).sum()
            out["years"] = len(yrs)
            out["pos_years"] = int(sum(by.get(k, 0) > 0 for k in yrs))     # zero trades -> not positive (m-10)
            for k in yrs:
                out[f"y{k}"] = by.get(k, np.nan)
        # swap (3.5): cost in R per trade per unit annual rate
        unit = (x.entry * x.nights / 365 / x.R).to_numpy()
        rate = self.cfg["costs"]["swap"]["scenario_s1_adverse_annual_rate"][n]
        out["swap_s1_e"] = r.mean() - rate * unit.mean()
        out["swap_s2_e"] = r.mean() - 2 * rate * unit.mean()
        be = r.mean() / unit.mean() if unit.mean() > 0 else np.inf
        out["swap_breakeven_rate"] = be if r.mean() > 0 else np.nan
        pip = self.cfg["pip_size"][n]
        out["swap_breakeven_pips_night"] = be * x.entry.mean() / 365 / pip if r.mean() > 0 else np.nan
        return out

    def sensitivity(self, n, src, tf, f, period="historical") -> dict:
        s = self.sens[n]
        x = s[(s.source == src) & (s.tf == tf) & (s["filter"] == f) & (s.status == "executed") & (s.period == period)]
        if n == "BTCUSD" and period == "historical":
            x = x[x.reclaim_close_t >= BTC_FROM]
        out = {f"E_{k}": v for k, v in x.groupby("scenario").r.mean().items()}
        base = self.executed(n, src, tf, f, period).r.mean()
        grid = [(0.5, out.get("E_spread_x0.5")), (1.0, base), (1.5, out.get("E_spread_x1.5")),
                (2.0, out.get("E_spread_x2")), (3.0, out.get("E_spread_x3"))]
        out["breakeven_spread_mult"] = _crossing(grid)
        out["breakeven_slip_mult"] = _crossing([(1.0, base), (2.0, out.get("E_slip_x2")), (4.0, out.get("E_slip_x4"))])
        return out


def _crossing(grid):
    g = [(m, e) for m, e in grid if e is not None and np.isfinite(e)]
    if not g:
        return np.nan
    if g[0][1] <= 0:
        return f"<{g[0][0]:g}x"
    for (m0, e0), (m1, e1) in zip(g, g[1:]):
        if e1 <= 0 < e0:
            return round(m0 + (m1 - m0) * e0 / (e0 - e1), 2)
    return f">{g[-1][0]:g}x"


def run_study(res: Path, cfg: dict, out: Path) -> dict:
    S = Study(res, cfg)
    insts = list(S.trades)
    fam = [(n, *c) for n in insts for c in FAMILY]
    unq = [(n, *c) for n in insts for c in UNEQUAL]
    boot = S.bootstrap(fam + unq)
    k = len(fam)
    mean, se, bm = boot["mean"], boot["se"], boot["boot"]
    t_obs = mean[:k] / se[:k]
    t_star = (bm[:, :k] - mean[:k]) / se[:k]
    p_rw = romano_wolf(np.nan_to_num(t_obs), t_star)

    rows = []
    for i, (n, src, tf, f) in enumerate(fam):
        m = S.metrics(n, src, tf, f)
        m.update(S.sensitivity(n, src, tf, f))
        m.update(boot_mean=mean[i], boot_se=se[i], t=t_obs[i], p_rw=p_rw[i],
                 ci_lo=np.nanpercentile(bm[:, i], 2.5), ci_hi=np.nanpercentile(bm[:, i], 97.5))
        # identical aligned set rule
        if f == "aligned":
            a = set(S.executed(n, src, tf, "aligned").sid)
            b = set(S.executed(n, src, tf, "none").sid)
            m["identical_to_none"] = a == b
        # placebos (4.5)
        if src == "pw":
            p = S.plac[n]
            p = p[(p.tf == tf) & (p.period == "historical")]
            m["placebo_draws"] = len(p)
            m["placebo_p95"] = np.nanpercentile(p.mean_r, 95) if len(p) else np.nan
            m["placebo_mean"] = p.mean_r.mean() if len(p) else np.nan
            m["beats_placebo"] = bool(len(p) and m.get("expectancy", -np.inf) > m["placebo_p95"])
            st_ = S.executed(n, "pw_stale", tf, "none").r
            m["stale_e"], m["stale_n"] = st_.mean(), len(st_)
        else:
            j = k + unq.index((n, "eq_unequal", tf, f))
            diff = bm[:, i] - bm[:, j]
            m["unequal_e"], m["unequal_n"] = mean[j], int(boot["N"][:, j].sum())
            m["diff_ci_lo"], m["diff_ci_hi"] = np.nanpercentile(diff, 2.5), np.nanpercentile(diff, 97.5)
            m["beats_placebo"] = bool(m["diff_ci_lo"] > 0)
        rows.append(m)
    df = pd.DataFrame(rows)
    # deflated Sharpe (M-14): variance of per-trade SR across the 54 cells
    var_sr = float(np.nanvar(df.sr_trade, ddof=1))
    for trials in cfg["v06"]["deflated_sharpe"]["trials"]:
        df[f"dsr_{trials}"] = [deflated_sharpe(r.sr_trade, r.executed, r.skew, r.kurt, var_sr, trials)
                               if r.executed > 3 else np.nan for r in df.itertuples()]
    df.attrs["var_sr"] = var_sr
    # exposed period, run once (criterion 8)
    ex = pd.DataFrame([S.metrics(n, s, tf, f, "exposed") for n, s, tf, f in fam])
    df["exposed_n"] = ex.executed.values
    df["exposed_e"] = ex.get("expectancy", pd.Series(np.nan, index=ex.index)).values
    # section 7 evidence bar
    mt = cfg["stats"]["min_trades"]
    df["c1_sig"] = (df.expectancy > 0) & (df.p_rw < 0.05)
    df["c1_bonf"] = df.t.abs() >= cfg["stats"]["bonferroni_t"]
    df["c2_trades"] = df.executed >= mt
    df["c3_years"] = df.pos_years >= np.where(df.instrument == "BTCUSD", 4, 9)
    df["c4_dirs"] = (df.long_e >= 0) & (df.short_e >= 0)
    df["c5_robust"] = (df["E_spread_x1.5"] > 0) & (df.swap_s1_e > 0) & (df["E_buffer_0.05"] > 0) & (df["E_buffer_0.2"] > 0)
    df["c6_placebo"] = df.beats_placebo
    df["c7_dsr"] = df["dsr_54"] > cfg["stats"]["deflated_sharpe_min"]
    df["c8_exposed"] = df.exposed_e >= 0
    cs = [c for c in df.columns if c.startswith("c") and c[1].isdigit() and c != "c1_bonf"]
    df["pass_all"] = df[cs].all(axis=1)
    df["unscorable_flag"] = df.unscorable_share > cfg["v06"]["unscorable_flag_share"]
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "family_54.csv", index=False)

    # descriptive PMH/PML (nominal only) and stale/unequal placebos
    desc = pd.DataFrame([{**S.metrics(n, *c), **S.sensitivity(n, *c)} for n in insts for c in DESCRIPTIVE])
    desc.to_csv(out / "pm_descriptive.csv", index=False)
    plc = pd.DataFrame([S.metrics(n, *c) for n in insts for c in STALE + UNEQUAL])
    plc.to_csv(out / "placebo_cells.csv", index=False)

    # 4.7 descriptive buckets (nominal statistics, never filters)
    buckets(S, fam, out)
    event_study(S, out)
    return {"family": df, "pm": desc, "placebo": plc}


def _bucket_frame(x: pd.DataFrame) -> pd.DataFrame:
    long = x.side == "low"
    depth = np.where(long, x.level - x.extreme, x.extreme - x.level) / x.atr
    body = np.where(x.rng > 0, (x.close - x.open_).abs() / x.rng.where(x.rng > 0), np.nan)
    cdist = np.where(long, x.close - x.level, x.level - x.close) / x.atr
    h = pd.to_datetime(x.t_entry, utc=True).dt.hour
    out = pd.DataFrame({
        "depth": pd.cut(depth, [-np.inf, 0.25, 0.5, 1.0, np.inf], labels=["<0.25", "0.25-0.5", "0.5-1.0", ">=1.0"], right=False),
        "speed": pd.cut(x.sweep_to_reclaim, [-1, 0, 3, 11, np.inf], labels=["same", "1-3", "4-11", "12+"]),
        "body": np.where(x.rng <= 0, "zero_range", pd.cut(body, [-np.inf, 0.33, 0.67, np.inf], labels=["<0.33", "0.33-0.67", ">0.67"]).astype(str)),
        "close_dist": pd.cut(cdist, [-np.inf, 0.1, 0.3, np.inf], labels=["<0.1", "0.1-0.3", ">0.3"], right=False),
        "vol_regime": pd.cut(x.vol_pct, [-np.inf, 33, 67, np.inf], labels=["<33", "33-67", ">67"], right=False),
        "trend": x.trend,
        "session": pd.cut(h, [-1, 6, 11, 20, 24], labels=["Asia 00-07", "London 07-12", "NY 12-21", "other"]),
        "gap_sweep": x.gap_sweep.astype(str),
        "touches": x.touches.clip(upper=4).astype(str),
        "nights": x.nights.clip(upper=3).astype(str),
        "direction": np.where(long, "long", "short"),
        "r": x.r,
    }, index=x.index)
    return out


def buckets(S: Study, fam, out: Path):
    rows = []
    for n, src, tf, f in fam:
        x = S.executed(n, src, tf, f)
        if not len(x):
            continue
        b = _bucket_frame(x)
        for var in [c for c in b.columns if c != "r"]:
            if src == "pw" and var == "touches":
                continue
            for lab, g in b.groupby(var, observed=True):
                r = g.r
                rows.append({"instrument": n, "source": src, "tf": tf, "filter": f, "variable": var, "bucket": str(lab),
                             "n": len(r), "mean_r": r.mean(),
                             "nominal_t": r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 2 and r.std() > 0 else np.nan})
    pd.DataFrame(rows).to_csv(out / "descriptive_buckets.csv", index=False)


def event_study(S: Study, out: Path):
    rows = []
    for n, sg in S.sigs.items():
        sg = sg[sg.reclaim_close_t < HIST_END]
        if n == "BTCUSD":
            sg = sg[sg.reclaim_close_t >= BTC_FROM]
        for (src, tf), g in sg.groupby(["source", "tf"]):
            for k in (1, 4, 12, 24):
                v = g[f"ev{k}"].dropna()
                rows.append({"instrument": n, "source": src, "tf": tf, "horizon_h": k, "n": len(v), "mean_atr": v.mean(),
                             "nominal_t": v.mean() / (v.std(ddof=1) / np.sqrt(len(v))) if len(v) > 2 else np.nan})
    pd.DataFrame(rows).to_csv(out / "event_study.csv", index=False)
