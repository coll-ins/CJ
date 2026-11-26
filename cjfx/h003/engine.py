"""H003 time-series momentum engine (docs/h003_spec.md v0.2). Pure functions, no I/O except loaders."""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import NormalDist

import numpy as np
import pandas as pd

NY = "America/New_York"
FX = ("EURUSD", "GBPUSD", "USDJPY")
SLIP = {"EURUSD": 0.00002, "GBPUSD": 0.00002, "USDJPY": 0.002, "XAUUSD": 0.05, "NAS100": 0.5, "BTCUSD": 5.0}
CAP = {"EURUSD": 4, "GBPUSD": 4, "USDJPY": 4, "XAUUSD": 2, "NAS100": 2, "BTCUSD": 1}
SERIES = {"EURUSD": "EURUSDm", "GBPUSD": "GBPUSDm", "USDJPY": "USDJPYm", "XAUUSD": "XAUUSDm",
          "NAS100": "USTECm", "BTCUSD": "BTCUSDm"}
SWAP_M = {"primary": 0.02, "stress": 0.04, "btc_primary": 0.10, "btc_stress": 0.20}


# ---------------------------------------------------------------- daily bars (3.1, A-4)
def daily_bars(m1: pd.DataFrame, btc: bool) -> pd.DataFrame:
    """m1: UTC-indexed M1 with bid_o, bid_c. Returns per trading day: close, exec_px, exec_how (UTC hour-of-week)."""
    ny = m1.index.tz_convert(NY)
    day = (ny + pd.Timedelta(hours=7)).normalize().tz_localize(None)   # 17:00 NY boundary, DST-aware
    df = pd.DataFrame({"o": m1["bid_o"].to_numpy(), "c": m1["bid_c"].to_numpy(), "day": day,
                       "nyh": ny.hour + ny.minute / 60, "utc": m1.index}, index=m1.index)
    g = df.groupby("day", sort=True)
    out = pd.DataFrame({"close": g["c"].last(), "n": g.size()})
    if not btc:
        out = out[out.index.dayofweek < 5]
        yr_med = out.groupby(out.index.year)["n"].transform("median")
        out = out[out["n"] >= 0.5 * yr_med]
    # execution: first bar at/after 03:00 NY within the day; within 60 min, else day's close
    cand = df[(df["nyh"] >= 3) & (df["nyh"] < 4)]
    first = cand.groupby("day").first()
    out["exec_px"] = first["o"].reindex(out.index)
    ex_utc = first["utc"].reindex(out.index)
    miss = out["exec_px"].isna()
    out.loc[miss, "exec_px"] = out.loc[miss, "close"]
    out["exec_how"] = (ex_utc.dt.dayofweek * 24 + ex_utc.dt.hour).fillna(-1).astype(int)
    out["exec_fallback"] = miss
    return out


# ---------------------------------------------------------------- spreads (4.1, A-3)
def spread_frac(days: pd.DataFrame, prof: pd.DataFrame, man: pd.DataFrame, mult: float = 1.0) -> np.ndarray:
    """Spread as a fraction of price at each day's execution bar."""
    prof = prof.merge(man[["month", "mean_mid", "median_spread"]], on="month")
    prof["frac"] = prof["median"] / prof["mean_mid"]
    month_med = (man.set_index("month")["median_spread"] / man.set_index("month")["mean_mid"])
    tab = prof.set_index(["month", "how"])["frac"]
    months = sorted(man["month"])
    first12 = prof[prof["month"].isin(months[:12])].groupby("how")["frac"].median()
    first12_all = float(month_med.loc[months[:12]].median())
    out = np.empty(len(days))
    for i, (d, how) in enumerate(zip(days.index, days["exec_how"].to_numpy())):
        mk = f"{d.year}-{d.month:02d}"
        if mk >= months[0]:
            v = tab.get((mk, how), np.nan)
            if not np.isfinite(v):
                v = month_med.get(mk, np.nan)
            if not np.isfinite(v):  # month not archived (e.g. latest): nearest earlier month
                prev = [m for m in months if m <= mk]
                v = float(month_med.loc[prev[-1]]) if prev else first12_all
        else:   # pre-archive: first 12 archived months, tagged extrapolated; x1.5 for 2000-2007
            v = first12.get(how, first12_all)
            if d.year <= 2007:
                v *= 1.5
        out[i] = v * mult
    return out


# ---------------------------------------------------------------- signal and positions (3.2-3.4)
@dataclass
class Params:
    lookbacks: tuple = (21, 63, 252)
    sigma_target: float = 0.10
    com: int = 60
    ann: int = 261
    cap: float = 4.0
    band: float = 0.25
    vol_scale: bool = True
    warmup: int = 252


def params_for(name: str) -> Params:
    if name == "BTCUSD":
        return Params(lookbacks=(30, 91, 365), ann=365, cap=CAP[name], warmup=365)
    return Params(cap=CAP[name])


def signal(close: pd.Series, p: Params) -> pd.Series:
    s = sum(np.sign(close / close.shift(L) - 1) for L in p.lookbacks) / len(p.lookbacks)
    s.iloc[: p.warmup] = np.nan
    return s


def sigma_hat(close: pd.Series, p: Params) -> pd.Series:
    r = np.log(close).diff()
    v = (r ** 2).ewm(com=p.com, min_periods=p.com).mean()
    return np.sqrt(v * p.ann)


def target_weights(close: pd.Series, p: Params, S: pd.Series | None = None) -> pd.Series:
    S = signal(close, p) if S is None else S
    if p.vol_scale:
        w = S * p.sigma_target / sigma_hat(close, p)
    else:   # fixed notional, scaled to the full-sample average so magnitudes are comparable (diagnostic only)
        w = S * p.sigma_target / float(sigma_hat(close, p).median())
    return w.clip(-p.cap, p.cap)


def held_weights(w_t: pd.Series, S: pd.Series, band: float) -> np.ndarray:
    """Weight held after the trade decided at each close (band rule 3.4)."""
    wt, s = w_t.to_numpy(), S.to_numpy()
    h = np.zeros(len(wt))
    cur, cur_s = 0.0, 0.0
    for i in range(len(wt)):
        if not np.isfinite(wt[i]):
            cur, cur_s = 0.0, 0.0
        elif s[i] != cur_s or abs(wt[i] - cur) > band * abs(wt[i]):
            cur, cur_s = wt[i], s[i]
        h[i] = cur
    return h


@dataclass
class Costs:
    spread: np.ndarray            # fraction of price at exec, per day
    slip_abs: float               # price units per side
    swap_m: float                 # annual
    btc: bool
    spread_mult: float = 1.0
    slip_mult: float = 1.0


def daily_returns(days: pd.DataFrame, held: np.ndarray, c: Costs) -> pd.DataFrame:
    """Return of day i (close i-1 -> close i). Decision at close i-1 executes at exec_px of day i."""
    C = days["close"].to_numpy()
    X = days["exec_px"].to_numpy()
    n = len(C)
    # held[i] = weight decided at close i, executed at exec bar of day i+1.
    # Day i: held[i-2] from close i-1 to exec_i (w_old), then held[i-1] to close i (w_new).
    w_old = np.r_[0.0, 0.0, held[:-2]][:n]
    w_new = np.r_[0.0, held[:-1]][:n]
    gross = (1 + w_old * (X / np.r_[np.nan, C[:-1]] - 1)) * (1 + w_new * (C / X - 1)) - 1
    gross[0] = 0.0
    dw = np.abs(w_new - w_old)
    tc = dw * (c.spread * c.spread_mult / 2 + c.slip_abs * c.slip_mult / X)
    if c.btc:
        nights = np.ones(n)
        denom = 365.0
    else:
        prev_wd = np.r_[-1, days.index.dayofweek[:-1]]
        nights = np.where(prev_wd == 2, 3.0, 1.0)
        denom = 360.0
    swap = np.abs(w_old) * c.swap_m * nights / denom
    out = pd.DataFrame({"gross": gross, "tcost": tc, "swap": swap, "w_old": w_old, "w_new": w_new,
                        "trade": dw > 0}, index=days.index)
    out["net"] = out["gross"] - out["tcost"] - out["swap"]
    out["net_ex_swap"] = out["gross"] - out["tcost"]
    return out


# ---------------------------------------------------------------- statistics (5)
def nw_t(x: np.ndarray, lag: int = 21) -> tuple[float, float]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    T = len(x)
    mu = x.mean()
    e = x - mu
    s = e @ e / T
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / T
    se = sqrt(max(s, 1e-30) / T)
    return mu / se, se


def stationary_bootstrap_means_fast(x: np.ndarray, draws: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """Vectorised stationary bootstrap (Politis-Romano): block lengths ~ geometric(1/block)."""
    x = np.asarray(x, float)
    T = len(x)
    out = np.empty(draws)
    for d in range(draws):
        n_blocks = int(T / block * 3) + 10
        L = rng.geometric(1.0 / block, size=n_blocks)
        S = rng.integers(0, T, size=n_blocks)
        cum = np.cumsum(L)
        k = int(np.searchsorted(cum, T)) + 1
        L, S = L[:k], S[:k]
        offs = np.arange(T) - np.repeat(np.r_[0, np.cumsum(L)[:-1]], L)[:T]
        idx = (np.repeat(S, L)[:T] + offs) % T
        out[d] = x[idx].mean()
    return out


def deflated_sharpe(x: np.ndarray, n_trials: int) -> float:
    x = np.asarray(x, float)
    T = len(x)
    sr = x.mean() / x.std(ddof=1)
    g3 = float(((x - x.mean()) ** 3).mean() / x.std() ** 3)
    g4 = float(((x - x.mean()) ** 4).mean() / x.std() ** 4)
    nd = NormalDist()
    gamma = 0.5772156649
    v = 1.0 / T
    sr0 = sqrt(v) * ((1 - gamma) * nd.inv_cdf(1 - 1 / n_trials) + gamma * nd.inv_cdf(1 - 1 / (n_trials * np.e)))
    den = sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    return nd.cdf((sr - sr0) * sqrt(T - 1) / den)


def block_sign_placebo(S: pd.Series, block: int, rng: np.random.Generator) -> pd.Series:
    """Permute the sign of S in blocks of `block` days; magnitude |S| kept (A-5)."""
    s = S.to_numpy().copy()
    valid = np.where(np.isfinite(s))[0]
    sg = np.sign(s[valid])
    nb = int(np.ceil(len(sg) / block))
    blocks = [sg[i * block:(i + 1) * block] for i in range(nb)]
    order = rng.permutation(nb)
    perm = np.concatenate([blocks[j] for j in order])[: len(sg)]
    s[valid] = np.abs(s[valid]) * perm
    return pd.Series(s, index=S.index)
