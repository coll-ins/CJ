"""Synthetic bid/ask M1 data for tests and smoke runs. Not market data; never use for research."""
from __future__ import annotations

import numpy as np
import pandas as pd


def random_walk_m1(start: str, end: str, seed: int = 1, price: float = 1.2, vol_pips: float = 0.6,
                   spread_pips: float = 0.2, pip: float = 1e-4) -> pd.DataFrame:
    idx = pd.date_range(start, end, freq="1min", tz="UTC", inclusive="left")
    ny = idx.tz_convert("America/New_York")
    # FX week: open Sunday 17:00 NY, close Friday 17:00 NY
    mins = ny.hour * 60 + ny.minute
    dow = ny.dayofweek
    open_ = ~((dow == 5) | ((dow == 4) & (mins >= 17 * 60)) | ((dow == 6) & (mins < 17 * 60)))
    idx = idx[open_]
    rng = np.random.default_rng(seed)
    n = len(idx)
    # heavy tails and volatility clustering so impulses and zones occur
    vol = np.exp(np.convolve(rng.normal(0, 0.35, n), np.ones(240) / 240 * 15, mode="same"))
    ret = rng.standard_t(3, n) * vol_pips * pip * vol
    mid_c = price + np.cumsum(ret)
    mid_o = np.r_[price, mid_c[:-1]]
    wig = np.abs(rng.normal(0, vol_pips * pip * 0.6, (2, n))) * vol
    mid_h = np.maximum(mid_o, mid_c) + wig[0]
    mid_l = np.minimum(mid_o, mid_c) - wig[1]
    half = spread_pips * pip / 2
    df = pd.DataFrame({
        "bid_o": mid_o - half, "bid_h": mid_h - half, "bid_l": mid_l - half, "bid_c": mid_c - half,
        "ask_o": mid_o + half, "ask_h": mid_h + half, "ask_l": mid_l + half, "ask_c": mid_c + half,
    }, index=pd.DatetimeIndex(idx, name="time"))
    return df


def mirror_m1(m1: pd.DataFrame, centre: float) -> pd.DataFrame:
    """Reflect prices around centre: bid' = 2c - ask, ask' = 2c - bid. A long on the original
    is exactly a short on the mirror."""
    out = pd.DataFrame(index=m1.index)
    for s_new, s_old in (("bid", "ask"), ("ask", "bid")):
        out[f"{s_new}_o"] = 2 * centre - m1[f"{s_old}_o"]
        out[f"{s_new}_c"] = 2 * centre - m1[f"{s_old}_c"]
        out[f"{s_new}_h"] = 2 * centre - m1[f"{s_old}_l"]
        out[f"{s_new}_l"] = 2 * centre - m1[f"{s_old}_h"]
    return out[["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]]
