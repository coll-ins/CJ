"""Exness MT5 Standard cost model.

Standard account: no commission; the cost is the spread (plus slippage and swap).
The backtest needs the spread *Exness* would have quoted, but Exness tick history
was not available when this was built. Until it is loaded, the ask used is

    ask_eff = bid + max(dukascopy_spread, floor)

where floor is costs.spread_floor_pips[pair] (an ESTIMATE, see config) or, once
Exness ticks are loaded, the median Exness spread for that pair and hour of week.
Dukascopy's own spread is kept where it is wider (news, rollover, thin markets).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ASK = ["ask_o", "ask_h", "ask_l", "ask_c"]
BID = ["bid_o", "bid_h", "bid_l", "bid_c"]


def apply_spread_floor(m1: pd.DataFrame, floor_price: float | np.ndarray) -> pd.DataFrame:
    out = m1.copy()
    for a, b in zip(ASK, BID):
        out[a] = out[b] + np.maximum(out[a] - out[b], floor_price)
    # keep the ask bar internally consistent
    out["ask_h"] = out[["ask_o", "ask_h", "ask_c"]].max(axis=1)
    out["ask_l"] = out[["ask_o", "ask_l", "ask_c"]].min(axis=1)
    return out


def hour_of_week(idx: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(idx.dayofweek * 24 + idx.hour)


def load_exness_ticks(path: str | Path) -> pd.DataFrame:
    """Load an Exness tick-history CSV (columns include Timestamp, Bid, Ask; names matched loosely)."""
    df = pd.read_csv(path)
    cols = {c.lower().strip('"'): c for c in df.columns}
    t = cols.get("timestamp") or cols.get("time") or cols.get("datetime")
    if not t or "bid" not in cols or "ask" not in cols:
        raise ValueError(f"unrecognised Exness tick file columns: {list(df.columns)}")
    out = pd.DataFrame({"bid": df[cols["bid"]].astype(float), "ask": df[cols["ask"]].astype(float)})
    out.index = pd.DatetimeIndex(pd.to_datetime(df[t], utc=True), name="time")
    return out.sort_index()


def exness_spread_profile(ticks: pd.DataFrame) -> pd.Series:
    """Median spread (price units) by UTC hour of week."""
    s = ticks["ask"] - ticks["bid"]
    return s.groupby(hour_of_week(ticks.index)).median()


def effective_m1(m1: pd.DataFrame, pair: str, cfg: dict, exness_profile: pd.Series | None = None) -> tuple[pd.DataFrame, dict]:
    costs = cfg["costs"]
    pip = cfg["pip_size"][pair]
    if exness_profile is not None and len(exness_profile):
        how = hour_of_week(m1.index)
        prof = exness_profile.reindex(range(168)).ffill().bfill().to_numpy()
        floor = prof[how]
        meta = {"spread_source": "exness_ticks_median_by_hour_of_week", "estimate": False}
    else:
        floor = costs["spread_floor_pips"][pair] * pip
        meta = {"spread_source": "dukascopy_with_floor", "floor_pips": costs["spread_floor_pips"][pair], "estimate": True}
    out = apply_spread_floor(m1, floor)
    sp = (out["ask_c"] - out["bid_c"]) / pip
    meta.update({"median_spread_pips": float(sp.median()), "p95_spread_pips": float(sp.quantile(0.95)),
                 "commission_per_lot": costs["commission_per_lot"],
                 "slippage_pips_per_side": (costs["slippage_pips_per_side"][pair] if isinstance(costs["slippage_pips_per_side"], dict) else costs["slippage_pips_per_side"])})
    return out, meta
