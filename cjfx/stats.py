"""Trade statistics and multiple-testing corrections."""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
from scipy import stats as sps


def summarize(r: np.ndarray, risk_pct: float = 0.5) -> dict:
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n == 0:
        return {"trades": 0}
    wins, losses = r[r > 0], r[r <= 0]
    sd = r.std(ddof=1) if n > 1 else np.nan
    t = r.mean() / (sd / math.sqrt(n)) if n > 1 and sd > 0 else np.nan
    eq = np.cumsum(r) * risk_pct
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    streak = cur = 0
    for x in r:
        cur = cur + 1 if x <= 0 else 0
        streak = max(streak, cur)
    return {
        "trades": n,
        "win_rate": float((r > 0).mean()),
        "avg_win_R": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_R": float(losses.mean()) if len(losses) else 0.0,
        "expectancy_R": float(r.mean()),
        "sd_R": float(sd),
        "t_stat": float(t),
        "p_one_sided": float(1 - sps.t.cdf(t, n - 1)) if np.isfinite(t) else np.nan,
        "profit_factor": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else np.inf,
        "total_R": float(r.sum()),
        "max_drawdown_pct": dd,
        "longest_losing_streak": int(streak),
    }


# ------------------------------------------------------------ return matrices

def weekly_matrix(trades: pd.DataFrame, start, end, key: str = "config_id") -> pd.DataFrame:
    """Sum of R per ISO week (by exit time) per configuration; weeks without trades are 0."""
    weeks = pd.date_range(pd.Timestamp(start).tz_localize(None).to_period("W").start_time,
                          pd.Timestamp(end).tz_localize(None), freq="W-MON")
    if trades.empty:
        return pd.DataFrame(index=weeks)
    wk = trades["exit_time"].dt.tz_localize(None).dt.to_period("W").dt.start_time
    m = trades.assign(week=wk).pivot_table(index="week", columns=key, values="R", aggfunc="sum")
    return m.reindex(weeks).fillna(0.0)


def _stationary_bootstrap_idx(T: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    p = 1.0 / mean_block
    idx = np.empty(T, dtype=np.int64)
    idx[0] = rng.integers(T)
    jumps = rng.random(T) < p
    starts = rng.integers(T, size=T)
    for t in range(1, T):
        idx[t] = starts[t] if jumps[t] else (idx[t - 1] + 1) % T
    return idx


def romano_wolf(X: np.ndarray, reps: int = 1000, mean_block: float = 4.0, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Romano-Wolf stepdown adjusted p-values for H0: mean <= 0, per column of X (T x N).

    Uses studentized means and a stationary block bootstrap to keep the cross-correlation
    and serial dependence between configurations. Returns (t_stats, adjusted_p).
    """
    X = np.asarray(X, dtype=float)
    T, N = X.shape
    mu = X.mean(0)
    sd = X.std(0, ddof=1)
    sd[sd == 0] = np.nan
    t = mu / (sd / np.sqrt(T))
    rng = np.random.default_rng(seed)
    boot = np.empty((reps, N))
    for b in range(reps):
        Xb = X[_stationary_bootstrap_idx(T, mean_block, rng)]
        sb = Xb.std(0, ddof=1)
        sb[sb == 0] = np.nan
        boot[b] = (Xb.mean(0) - mu) / (sb / np.sqrt(T))
    boot = np.nan_to_num(boot, nan=-np.inf)
    tt = np.nan_to_num(t, nan=-np.inf)
    order = np.argsort(-tt)
    # max over the still-remaining hypotheses = reverse cumulative max in sorted order
    tail_max = np.maximum.accumulate(boot[:, order][:, ::-1], axis=1)[:, ::-1]
    p_adj = np.ones(N)
    prev = 0.0
    for r, j in enumerate(order):
        p = float((tail_max[:, r] >= tt[j]).mean())
        prev = max(prev, p)
        p_adj[j] = prev
    return t, p_adj


def bonferroni_t(n_tests: int, n_obs: int, alpha: float = 0.05) -> float:
    return float(sps.t.ppf(1 - alpha / n_tests, max(n_obs - 1, 1)))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    g = 0.5772156649
    if n_trials < 2:
        return 0.0
    return math.sqrt(var_sr) * ((1 - g) * sps.norm.ppf(1 - 1 / n_trials) + g * sps.norm.ppf(1 - 1 / (n_trials * math.e)))


def deflated_sharpe(r: np.ndarray, n_trials: int, var_sr_trials: float) -> dict:
    """Bailey and Lopez de Prado deflated Sharpe ratio (per-period, non-annualised)."""
    r = np.asarray(r, dtype=float)
    T = len(r)
    if T < 3 or r.std(ddof=1) == 0:
        return {"dsr": np.nan}
    sr = r.mean() / r.std(ddof=1)
    sk = float(sps.skew(r))
    ku = float(sps.kurtosis(r, fisher=False))
    sr0 = expected_max_sharpe(n_trials, var_sr_trials)
    denom = math.sqrt(max(1e-12, 1 - sk * sr + (ku - 1) / 4 * sr ** 2))
    z = (sr - sr0) * math.sqrt(T - 1) / denom
    return {"sharpe": float(sr), "sr0_expected_max": float(sr0), "dsr": float(sps.norm.cdf(z)),
            "n_trials": int(n_trials), "skew": sk, "kurtosis": ku}


def pbo_cscv(X: np.ndarray, n_blocks: int = 16) -> dict:
    """Probability of backtest overfitting by combinatorially symmetric cross-validation.

    X: T x N performance matrix (e.g. weekly R per configuration). Ranks use the mean.
    """
    X = np.asarray(X, dtype=float)
    T, N = X.shape
    if N < 2 or T < n_blocks:
        return {"pbo": np.nan, "combinations": 0}
    edges = np.linspace(0, T, n_blocks + 1).astype(int)
    bs = np.array([X[edges[i]:edges[i + 1]].sum(0) for i in range(n_blocks)])
    bc = np.diff(edges).astype(float)
    combos = np.array(list(itertools.combinations(range(n_blocks), n_blocks // 2)))
    M = np.zeros((len(combos), n_blocks))
    M[np.arange(len(combos))[:, None], combos] = 1.0
    is_mean = (M @ bs) / (M @ bc)[:, None]
    oos_mean = ((1 - M) @ bs) / ((1 - M) @ bc)[:, None]
    best = is_mean.argmax(1)
    oos_best = oos_mean[np.arange(len(combos)), best]
    rank = (oos_mean < oos_best[:, None]).sum(1) + 0.5 * ((oos_mean == oos_best[:, None]).sum(1) - 1)
    w = (rank + 1) / (N + 1)
    logit = np.log(w / (1 - w))
    return {"pbo": float((logit <= 0).mean()), "combinations": int(len(combos)),
            "median_logit": float(np.median(logit))}
