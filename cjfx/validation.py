"""Walk-forward selection, multiple-testing corrections, verdicts and the one-shot holdout."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import GRID_KEYS
from .stats import (bonferroni_t, deflated_sharpe, pbo_cscv, romano_wolf, summarize,
                    weekly_matrix)

STRAT_KEYS = ["execution", "setup_type"]


def _ts(y: int) -> pd.Timestamp:
    return pd.Timestamp(f"{y}-01-01", tz="UTC")


def select_config(train: pd.DataFrame, min_trades: int) -> tuple[str | None, pd.DataFrame]:
    g = train.groupby("config_id")["R"].agg(["count", "mean"])
    elig = g[g["count"] >= min_trades]
    if elig.empty:
        return None, g
    best = elig["mean"].max()
    pick = sorted(elig.index[elig["mean"] == best])[0]
    return pick, g


def walk_forward_strategy(tr: pd.DataFrame, cfg: dict) -> dict:
    v = cfg["validation"]
    wf = v["walk_forward"]
    y0 = pd.Timestamp(wf["start"]).year
    y1 = pd.Timestamp(wf["end"]).year
    ty, sy = wf["train_years"], wf["test_years"]
    folds, oos = [], []
    for Y in range(y0 + ty, y1 + 1, sy):
        tr_s, tr_e = _ts(Y - ty), _ts(Y)
        te_s, te_e = _ts(Y), _ts(Y + sy)
        train = tr[(tr["entry_time"] >= tr_s) & (tr["exit_time"] < tr_e)]  # drop trades straddling the split
        pick, g = select_config(train, v["min_train_trades"])
        rec = {"test_year": Y, "picked": pick, "train_trades_best": int(g["count"].max()) if len(g) else 0}
        if pick is None:
            rec["status"] = "sat_out_insufficient_train_trades"
            folds.append(rec)
            continue
        rec["is_expectancy"] = float(g.loc[pick, "mean"])
        rec["is_trades"] = int(g.loc[pick, "count"])
        test = tr[(tr["config_id"] == pick) & (tr["entry_time"] >= te_s) & (tr["entry_time"] < te_e)]
        rec["oos_trades"] = int(len(test))
        rec["oos_expectancy"] = float(test["R"].mean()) if len(test) else None
        rec["status"] = "ok"
        folds.append(rec)
        oos.append(test.assign(fold=Y))
    oos_df = pd.concat(oos) if oos else tr.iloc[0:0]
    return {"folds": folds, "oos": oos_df}


def stability(folds: list[dict]) -> dict:
    picks = [f["picked"].split("|") for f in folds if f.get("picked")]
    out = {}
    for i, k in enumerate(GRID_KEYS):
        opts = [p[i] for p in picks]
        if not opts:
            out[k] = {"mode": None, "share": 0.0, "folds": 0}
            continue
        s = pd.Series(opts).value_counts()
        out[k] = {"mode": s.index[0], "share": float(s.iloc[0] / len(folds)), "folds": len(opts),
                  "counts": s.to_dict()}
    return out


def evaluate(trades: pd.DataFrame, cfg: dict, n_trials: int, n_grid: int) -> dict:
    """Full research report over the walk-forward period. Never touches the holdout."""
    v = cfg["validation"]
    vd = v["verdict"]
    wf = v["walk_forward"]
    start, end = pd.Timestamp(wf["start"], tz="UTC"), pd.Timestamp(wf["end"], tz="UTC") + pd.Timedelta(days=1)
    tr = trades[(trades["entry_time"] >= start) & (trades["entry_time"] < end)].copy()
    # strategy = instrument x execution x setup type; instruments are never pooled
    tr["strategy"] = tr["pair"] + ":" + tr["execution"] + ":" + tr["setup_type"]
    tr["col"] = tr["strategy"] + "#" + tr["config_id"]
    W_all = weekly_matrix(tr, start, end, key="col")
    n_configs_total = max(n_grid, W_all.shape[1], 1)  # configs with zero trades were still tried
    rw_t, rw_p = (romano_wolf(W_all.to_numpy(), v["bootstrap_reps"], v["bootstrap_mean_block_weeks"])
                  if W_all.shape[1] else (np.array([]), np.array([])))
    rw = pd.DataFrame({"t_weekly": rw_t, "p_romano_wolf": rw_p}, index=W_all.columns)
    sr_all = (W_all.mean() / W_all.std(ddof=1)).replace([np.inf, -np.inf], np.nan).dropna()
    var_sr = float(sr_all.var(ddof=1)) if len(sr_all) > 1 else 0.0
    n_trials_eff = max(n_trials, n_configs_total)
    report = {"generated": datetime.now(timezone.utc).isoformat(), "period": [str(start.date()), str(end.date())],
              "n_configurations_tested": int(n_configs_total), "n_trials_for_dsr": int(n_trials_eff),
              "strategies": {}}
    pairs = [p for p in cfg["instruments"] if p in set(tr["pair"])] or sorted(set(tr["pair"]))
    import itertools as _it
    for pair, ex, stp in _it.product(pairs, cfg["strategies"]["execution"], cfg["strategies"]["setup_type"]):
        if True:
            key = f"{pair}:{ex}:{stp}"
            s_tr = tr[tr["strategy"] == key]
            res = {"in_sample_all_configs_trades": int(len(s_tr))}
            if s_tr.empty:
                res["verdict"] = "insufficient_evidence"
                res["reason"] = "no trades in any configuration"
                report["strategies"][key] = res
                continue
            per_cfg = s_tr.groupby("config_id")["R"].apply(lambda r: pd.Series(summarize(r.to_numpy()))).unstack()
            per_cfg = per_cfg.sort_values("expectancy_R", ascending=False)
            best_id = per_cfg.index[0]
            best_r = s_tr[s_tr["config_id"] == best_id]["R"].to_numpy()
            bt = bonferroni_t(n_configs_total, len(best_r), v["alpha"])
            report["bonferroni_t_threshold_at_best_n"] = bt
            # walk-forward
            wfres = walk_forward_strategy(s_tr, cfg)
            oos = wfres["oos"]
            oos_sum = summarize(oos["R"].to_numpy()) if len(oos) else {"trades": 0}
            per_pair = {p: summarize(g["R"].to_numpy()) for p, g in oos.groupby("pair")} if len(oos) else {}
            ok_folds = [f for f in wfres["folds"] if f["status"] == "ok"]
            is_mean = np.mean([f["is_expectancy"] for f in ok_folds]) if ok_folds else np.nan
            wfe = (oos_sum.get("expectancy_R", np.nan) / is_mean) if ok_folds and is_mean > 0 else np.nan
            stab = stability(wfres["folds"])
            W = weekly_matrix(s_tr, start, end, key="config_id")
            pbo = pbo_cscv(W.to_numpy(), v["pbo_blocks"])
            W_oos = weekly_matrix(oos, start, end, key="pair").sum(axis=1) if len(oos) else pd.Series(dtype=float)
            dsr_best = deflated_sharpe(W[best_id].to_numpy(), n_trials_eff, var_sr)
            dsr_oos = deflated_sharpe(W_oos.to_numpy(), n_trials_eff, var_sr) if len(W_oos) else {"dsr": np.nan}
            rw_s = rw.loc[[c for c in rw.index if c.startswith(key + "#")]]
            checks = {}
            n_oos = oos_sum.get("trades", 0)
            checks["sample_size"] = n_oos >= vd["min_oos_trades"]
            checks["wf_expectancy_t"] = bool(n_oos > 1 and oos_sum["expectancy_R"] > 0 and oos_sum["t_stat"] >= vd["min_t_stat"])
            checks["pairs_positive"] = sum(1 for p in per_pair.values() if p.get("expectancy_R", 0) > 0) >= vd["min_pairs_positive"]
            checks["wf_efficiency"] = bool(np.isfinite(wfe) and wfe >= vd["min_wf_efficiency"])
            checks["pbo"] = bool(np.isfinite(pbo["pbo"]) and pbo["pbo"] < vd["max_pbo"])
            checks["dsr"] = bool(np.isfinite(dsr_oos.get("dsr", np.nan)) and dsr_oos["dsr"] > vd["min_dsr"])
            checks["stability_all_params"] = all(x["share"] >= vd["stability_min_share"] for x in stab.values())
            if not checks["sample_size"]:
                verdict = "insufficient_evidence"
            elif all(checks.values()):
                verdict = "pass_pending_holdout"
            else:
                verdict = "fail"
            res.update({
                "verdict": verdict, "checks": checks,
                "walk_forward_oos": oos_sum, "walk_forward_oos_by_pair": per_pair,
                "walk_forward_efficiency": wfe, "folds": wfres["folds"], "stability": stab,
                "pbo": pbo, "dsr_best_full_period_config": dsr_best, "dsr_walk_forward_oos": dsr_oos,
                "best_full_period_config": {"config_id": best_id, **summarize(best_r),
                                            "bonferroni_t_needed": bt},
                "romano_wolf": {"configs": int(len(rw_s)), "min_adjusted_p": float(rw_s["p_romano_wolf"].min()) if len(rw_s) else None,
                                "significant_at_alpha": int((rw_s["p_romano_wolf"] <= v["alpha"]).sum())},
                "top_configs_in_sample": per_cfg.head(10).reset_index().to_dict("records"),
            })
            report["strategies"][key] = res
    return report


# ---------------------------------------------------------------- holdout

def run_holdout(trades: pd.DataFrame, cfg: dict, ledger_path: Path, strategy: str, force: bool = False) -> dict:
    """Select with the walk-forward rule on the last train window before the holdout, then
    trade the holdout once. Refuses a second run unless force=True (which is recorded)."""
    v = cfg["validation"]
    ho = v["holdout"]
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {"runs": []}
    prior = [r for r in ledger["runs"] if r["strategy"] == strategy]
    if len(prior) >= ho["runs_allowed"] and not force:
        raise PermissionError(f"holdout already run {len(prior)}x for {strategy}; it is no longer a holdout")
    hs = pd.Timestamp(ho["start"], tz="UTC")
    ty = v["walk_forward"]["train_years"]
    pair, ex, stp = strategy.split(":")
    s_tr = trades[(trades["pair"] == pair) & (trades["execution"] == ex) & (trades["setup_type"] == stp)]
    train = s_tr[(s_tr["entry_time"] >= hs - pd.DateOffset(years=ty)) & (s_tr["exit_time"] < hs)]
    pick, _ = select_config(train, v["min_train_trades"])
    out = {"strategy": strategy, "ts": datetime.now(timezone.utc).isoformat(), "picked": pick, "forced": force}
    if pick is None:
        out["result"] = "no configuration had enough training trades"
    else:
        test = s_tr[(s_tr["config_id"] == pick) & (s_tr["entry_time"] >= hs)]
        out["holdout"] = summarize(test["R"].to_numpy())
        out["holdout_by_pair"] = {p: summarize(g["R"].to_numpy()) for p, g in test.groupby("pair")}
        # drawdown check against bootstrapped walk-forward drawdowns
        wf = walk_forward_strategy(s_tr[s_tr["entry_time"] < hs], cfg)["oos"]["R"].to_numpy()
        if len(wf) and len(test):
            rng = np.random.default_rng(11)
            risk = cfg["risk"]["per_trade_pct"]
            dds = []
            for _ in range(2000):
                eq = np.cumsum(rng.choice(wf, size=len(test), replace=True)) * risk
                dds.append((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
            lim = float(np.percentile(dds, v["verdict"]["holdout_dd_percentile"]))
            out["dd_limit_pct"] = lim
            out["pass"] = bool(out["holdout"]["expectancy_R"] > 0 and out["holdout"]["max_drawdown_pct"] <= lim)
    ledger["runs"].append({k: out[k] for k in ("strategy", "ts", "picked", "forced")})
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2))
    return out
