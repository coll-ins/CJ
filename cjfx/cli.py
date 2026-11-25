"""Command line: download -> bars -> grid -> evaluate -> (once) holdout.

  python -m cjfx.cli download --start 2011-01-01 --end 2026-11-24
  python -m cjfx.cli bars
  python -m cjfx.cli grid
  python -m cjfx.cli evaluate
  python -m cjfx.cli sensitivity --strategy swing_h1:continuation --grid-point "consecutive_3|h1_swing|sweep_wick|fixed_3r|london_ny"
  python -m cjfx.cli holdout --strategy swing_h1:continuation      # runs once per strategy
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config, numeric_fixed_keys, scaled
from .costs import effective_m1, exness_spread_profile, load_exness_ticks
from .data import dukascopy
from .data.bars import build_all, quality_report
from .research import audit_sample, grid_size, log_trials, one_open_trade_per_pair, run_pair, trial_count
from .stats import summarize
from .validation import evaluate, run_holdout


def _json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def m1_path(d: Path, pair: str) -> Path:
    return d / "m1" / f"{pair}_M1.parquet"


def cmd_download(a, cfg):
    data = Path(a.data)
    for pair in a.pairs or cfg["instruments"]:
        print(f"downloading {pair} {a.start}..{a.end}", flush=True)
        m1 = dukascopy.download_range(pair, date.fromisoformat(a.start), date.fromisoformat(a.end),
                                      data / "raw" / "dukascopy", workers=a.workers)
        out = m1_path(data, pair)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and not a.overwrite:
            old = pd.read_parquet(out)
            m1 = pd.concat([old, m1]).sort_index()
            m1 = m1[~m1.index.duplicated(keep="last")]
        m1.to_parquet(out)
        print(f"  {pair}: {len(m1):,} M1 bars -> {out}")


def load_bars(data: Path, pair: str, cfg: dict) -> tuple[dict, dict, str]:
    m1 = pd.read_parquet(m1_path(data, pair))
    prof = None
    ex = data / "exness" / f"{pair}.csv"
    if ex.exists():
        prof = exness_spread_profile(load_exness_ticks(ex))
    m1e, meta = effective_m1(m1, pair, cfg, prof)
    h = hashlib.sha256(pd.util.hash_pandas_object(m1.iloc[:: max(1, len(m1) // 5000)]).values.tobytes()).hexdigest()[:16]
    return build_all(m1e, cfg["calendar"]), meta, h


def cmd_bars(a, cfg):
    data = Path(a.data)
    rep = {}
    for pair in a.pairs or cfg["instruments"]:
        m1 = pd.read_parquet(m1_path(data, pair))
        q = quality_report(m1, cfg["calendar"])
        bars, meta, h = load_bars(data, pair, cfg)
        q.update({"costs": meta, "bars": {k: len(v) for k, v in bars.items()}, "data_hash": h})
        rep[pair] = q
        print(pair, json.dumps({k: q[k] for k in ("m1_bars", "first", "last", "gaps_over_limit_in_trading_time")}, default=_json))
    out = Path(a.results) / "data_quality.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, default=_json))


def run_grid(cfg, data: Path, pairs, news, label: str, results: Path, grid_override=None, log=print):
    all_tr, all_rj, metas, hashes = [], [], {}, []
    for pair in pairs:
        bars, meta, h = load_bars(data, pair, cfg)
        metas[pair] = meta
        hashes.append(h)
        tr, rj = run_pair(pair, bars, cfg, news, grid_override, log=log)
        all_tr.append(tr)
        all_rj.append(rj)
        log(f"  {pair}: {len(tr):,} raw trades")
    tr = pd.concat([t for t in all_tr if len(t)]) if any(len(t) for t in all_tr) else pd.DataFrame()
    rj = pd.concat([r for r in all_rj if len(r)]) if any(len(r) for r in all_rj) else pd.DataFrame()
    tr = one_open_trade_per_pair(tr)
    c = dict(cfg)
    if grid_override:
        c["grid"] = {**cfg["grid"], **grid_override}
    log_trials(results / "trials.jsonl", cfg, grid_size(c), label, "-".join(hashes))
    return tr, rj, metas


def cmd_grid(a, cfg):
    data, results = Path(a.data), Path(a.results)
    news = pd.read_csv(a.news) if a.news else None
    tr, rj, metas = run_grid(cfg, data, a.pairs or cfg["instruments"], news, "grid", results)
    results.mkdir(parents=True, exist_ok=True)
    tr.to_parquet(results / "trades.parquet")
    if len(rj):
        rj.to_parquet(results / "rejects.parquet")
    if len(tr):
        audit_sample(tr).to_csv(results / "audit_sample_20_trades.csv", index=False)
    (results / "cost_model.json").write_text(json.dumps({**metas, "news_filter_applied": news is not None}, indent=2, default=_json))
    print(f"{len(tr):,} trades after one-open-trade-per-pair -> {results / 'trades.parquet'}")


def cmd_evaluate(a, cfg):
    results = Path(a.results)
    tr = pd.read_parquet(results / "trades.parquet")
    rep = evaluate(tr, cfg, trial_count(results / "trials.jsonl"), grid_size(cfg))
    cm = results / "cost_model.json"
    if cm.exists():
        rep["cost_model"] = json.loads(cm.read_text())
    (results / "report.json").write_text(json.dumps(rep, indent=2, default=_json))
    print(f"{'strategy':32s} {'verdict':24s} {'OOS n':>6s} {'E[R]':>7s} {'t':>6s} {'PBO':>5s}")
    for k, s in rep["strategies"].items():
        o = s.get("walk_forward_oos", {})
        print(f"{k:32s} {s['verdict']:24s} {o.get('trades', 0):6d} {o.get('expectancy_R', float('nan')):7.3f} "
              f"{o.get('t_stat', float('nan')):6.2f} {s.get('pbo', {}).get('pbo', float('nan')):5.2f}")


def cmd_sensitivity(a, cfg):
    data, results = Path(a.data), Path(a.results)
    ex, stp = a.strategy.split(":")
    zb, liq, st, exi, ses = a.grid_point.split("|")
    override = {"zone_base": [zb], "liquidity": [liq], "stop": [st], "exit": [exi], "entry_sessions": [ses]}
    wf = cfg["validation"]["walk_forward"]
    lo, hi = pd.Timestamp(wf["start"], tz="UTC"), pd.Timestamp(wf["end"], tz="UTC") + pd.Timedelta(days=1)
    rows = []
    variants = [("base", 1.0, cfg)] + [(k, f, scaled(cfg, k, f)) for k in numeric_fixed_keys(cfg)
                                       for f in cfg["validation"]["sensitivity_scale"]]
    for key, f, c in variants:
        c = {**c, "strategies": {**c["strategies"], "execution": [ex]}}
        tr, _, _ = run_grid(c, data, a.pairs or cfg["instruments"], None, f"sensitivity:{key}:{f}", results, override, log=lambda *x: None)
        tr = tr[(tr["setup_type"] == stp) & (tr["entry_time"] >= lo) & (tr["entry_time"] < hi)] if len(tr) else tr
        s = summarize(tr["R"].to_numpy()) if len(tr) else {"trades": 0}
        rows.append({"param": key, "factor": f, **s})
        print(f"{key:40s} x{f:<5} n={s.get('trades', 0):5d} E[R]={s.get('expectancy_R', float('nan')):.3f}")
    pd.DataFrame(rows).to_csv(results / f"sensitivity_{ex}_{stp}.csv", index=False)


def cmd_holdout(a, cfg):
    results = Path(a.results)
    tr = pd.read_parquet(results / "trades.parquet")
    out = run_holdout(tr, cfg, results / "holdout_ledger.json", a.strategy, force=a.force)
    print(json.dumps(out, indent=2, default=_json))
    (results / f"holdout_{a.strategy.replace(':', '_')}.json").write_text(json.dumps(out, indent=2, default=_json))


def main(argv=None):
    p = argparse.ArgumentParser(prog="cjfx")
    p.add_argument("--config", default=None)
    p.add_argument("--data", default="data")
    p.add_argument("--results", default="results")
    p.add_argument("--pairs", type=lambda x: [s.strip().upper() for s in x.split(",") if s.strip()],
                   help="comma-separated, default: config instruments")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download")
    d.add_argument("--start", default="2011-01-01")
    d.add_argument("--end", default=str(date.today()))
    d.add_argument("--workers", type=int, default=6)
    d.add_argument("--overwrite", action="store_true")
    sub.add_parser("bars")
    g = sub.add_parser("grid")
    g.add_argument("--news", help="CSV with time_utc,currency,impact (high-impact events)")
    sub.add_parser("evaluate")
    s = sub.add_parser("sensitivity")
    s.add_argument("--strategy", required=True)
    s.add_argument("--grid-point", required=True, help='e.g. "consecutive_3|h1_swing|sweep_wick|fixed_3r|london_ny"')
    h = sub.add_parser("holdout")
    h.add_argument("--strategy", required=True)
    h.add_argument("--force", action="store_true", help="re-run a used holdout (recorded; result no longer counts)")
    a = p.parse_args(argv)
    cfg = load_config(a.config)
    {"download": cmd_download, "bars": cmd_bars, "grid": cmd_grid, "evaluate": cmd_evaluate,
     "sensitivity": cmd_sensitivity, "holdout": cmd_holdout}[a.cmd](a, cfg)


if __name__ == "__main__":
    sys.exit(main())
