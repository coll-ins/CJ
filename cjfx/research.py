"""Run the full H001 grid on one pair and return one row per simulated trade."""
from __future__ import annotations

import itertools
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import levels as levels_mod
from .config import config_hash
from .engine import EXEC_TF, EntryFilter, ExecContext, scan
from .market import Market
from .sim import Trade, simulate
from .zones import find_zones


def _px(x: float, d: int) -> float:
    """Direction-space price back to a real market price (zone top/bottom swap meaning for shorts)."""
    return float(x) * d


def run_pair(pair: str, bars: dict[str, pd.DataFrame], cfg: dict, news: pd.DataFrame | None = None,
             grid_override: dict | None = None, log=print) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (trades, rejects). Trades are before the one-open-trade-per-pair filter."""
    g = dict(cfg["grid"])
    if grid_override:
        g.update(grid_override)
    fx = cfg["fixed_for_now"]
    rows, rejects = [], []
    mkts = {d: Market(pair, bars, cfg, d) for d in (1, -1)}
    zones = {(d, zb): find_zones(mkts[d].tf["H4"], fx, zb) for d in (1, -1) for zb in g["zone_base"]}
    for (d, zb), zs in zones.items():
        log(f"  {pair} {'long' if d == 1 else 'short'} {zb}: {len(zs)} H4 zones")
    lv = {(d, L): levels_mod.compute(mkts[d], cfg, L) for d in (1, -1) for L in g["liquidity"]}
    ctxs = {(d, ex): ExecContext(mkts[d].tf[EXEC_TF[ex]], fx["swing_k"][EXEC_TF[ex].lower()])
            for d in (1, -1) for ex in cfg["strategies"]["execution"]}
    for d in (1, -1):
        mkt = mkts[d]
        for ex, zb, L, ses in itertools.product(cfg["strategies"]["execution"], g["zone_base"], g["liquidity"], g["entry_sessions"]):
            filt = EntryFilter(cfg, cfg["calendar"]["entry_session_sets"][ses], pair, news)
            setups = scan(zones[(d, zb)], mkt, lv[(d, L)], ex, ctxs[(d, ex)], filt, cfg)
            opp = zones[(-d, zb)]
            for st in setups:
                if st.setup_type is None:
                    rejects.append({"pair": pair, "direction": d, "execution": ex, "zone_base": zb, "liquidity": L,
                                    "entry_sessions": ses, "entry_time": st.entry_time, "reason": "neutral_bias"})
                    continue
                for sm, em in itertools.product(g["stop"], g["exit"]):
                    res = simulate(st, sm, em, mkt, ctxs[(d, ex)], opp, cfg)
                    base = {"pair": pair, "direction": d, "execution": ex, "setup_type": st.setup_type,
                            "zone_base": zb, "liquidity": L, "stop": sm, "exit": em, "entry_sessions": ses}
                    if isinstance(res, str):
                        rejects.append({**base, "entry_time": st.entry_time, "reason": res})
                        continue
                    rows.append({**base, "zone_id": st.zone_id, "first_touch": st.first_touch,
                                 "zone_near_edge": _px(st.zone_top, d), "zone_far_edge": _px(st.zone_bottom, d),
                                 "liquidity_level": _px(st.level, d), "sweep_time": st.sweep_time,
                                 "sweep_extreme": _px(st.sweep_low, d), "confirm_time": st.confirm_time,
                                 "confirm_swing": _px(st.conf_swing_high, d), "confirm_pullback": _px(st.conf_swing_low, d),
                                 "entry_time": res.entry_time, "exit_time": res.exit_time, "entry": _px(res.entry, d),
                                 "stop_px": _px(res.stop, d), "target_px": _px(res.target, d), "r_dist_pips": res.r_dist / mkt.pip,
                                 "spread_pips": res.spread_at_entry / mkt.pip, "R": res.r_mult,
                                 "swap_R": res.swap_r, "exit_reason": res.exit_reason,
                                 "bias_mn": st.bias_mn, "bias_w": st.bias_w})
    tr = pd.DataFrame(rows)
    if len(tr):
        tr["config_id"] = tr[["zone_base", "liquidity", "stop", "exit", "entry_sessions"]].agg("|".join, axis=1)
        for c in ("entry_time", "exit_time", "first_touch", "sweep_time", "confirm_time"):
            tr[c] = pd.to_datetime(tr[c], utc=True)
    rj = pd.DataFrame(rejects)
    if len(rj):
        rj["entry_time"] = pd.to_datetime(rj["entry_time"], utc=True)
    return tr, rj


def grid_size(cfg: dict) -> int:
    g = cfg["grid"]
    n = 1
    for k in ("zone_base", "liquidity", "stop", "exit", "entry_sessions"):
        n *= len(g[k])
    return n * len(cfg["strategies"]["execution"]) * len(cfg["strategies"]["setup_type"])


def audit_sample(tr: pd.DataFrame, n: int = 20, seed: int = 0) -> pd.DataFrame:
    """Random trades of the primary configuration for hand-checking against charts."""
    prim = tr[(tr["zone_base"] == "consecutive_3") & (tr["exit"] == "fixed_3r")]
    if prim.empty:
        prim = tr
    return prim.sample(min(n, len(prim)), random_state=seed).sort_values("entry_time")


def one_open_trade_per_pair(tr: pd.DataFrame) -> pd.DataFrame:
    """Within each strategy, config and pair, skip a trade that enters while another is open."""
    if tr.empty:
        return tr
    keep = np.zeros(len(tr), dtype=bool)
    tr = tr.sort_values("entry_time").reset_index(drop=True)
    for _, idx in tr.groupby(["execution", "setup_type", "config_id", "pair"]).groups.items():
        busy_until = None
        for i in idx:
            if busy_until is None or tr.at[i, "entry_time"] >= busy_until:
                keep[i] = True
                busy_until = tr.at[i, "exit_time"]
    return tr[keep].reset_index(drop=True)


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def log_trials(path: Path, cfg: dict, n_configs: int, label: str, data_hash: str) -> None:
    """Append-only trial ledger: every grid run counts toward the deflated Sharpe trial count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "label": label, "config_hash": config_hash(cfg),
           "n_configs": n_configs, "commit": git_commit(), "data_hash": data_hash}
    with open(path, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def trial_count(path: Path) -> int:
    if not path.exists():
        return 0
    seen = set()
    total = 0
    for line in path.read_text().splitlines():
        r = json.loads(line)
        key = (r["config_hash"], r["label"], r["data_hash"], r["commit"])
        if key in seen:
            continue  # identical code + config + data rerun is not a new trial
        seen.add(key)
        total += r["n_configs"]
    return total
