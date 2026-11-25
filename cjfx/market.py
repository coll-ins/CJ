"""Per-pair market view in "direction space".

All rules are written once, for longs. Shorts run the same code on mirrored prices:
signal prices are negated (and high/low swapped), the entry side becomes the bid and
the exit side becomes the ask. In long space: signal = bid, entry fills at ask,
stops/targets trigger on bid. In short space: entry fills at bid, stops/targets trigger
on ask. Spread therefore costs the trader on both sides exactly as on MT5.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .indicators import atr, structure_state


@dataclass
class Series:
    t_open: np.ndarray   # int64 ns UTC
    t_close: np.ndarray  # int64 ns UTC
    o: np.ndarray        # signal side (bid), direction space
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    eo: np.ndarray       # entry side open
    xo: np.ndarray       # exit side o/h/l/c
    xh: np.ndarray
    xl: np.ndarray
    xc: np.ndarray
    atr: np.ndarray | None = None

    def __len__(self):
        return len(self.o)

    def idx_closed_by(self, t: int) -> int:
        """Index of the last bar whose close_time <= t (-1 if none)."""
        return int(np.searchsorted(self.t_close, t, side="right")) - 1

    def idx_open_at_or_after(self, t: int) -> int:
        return int(np.searchsorted(self.t_open, t, side="left"))


def to_series(df: pd.DataFrame, direction: int, atr_n: int | None = None) -> Series:
    if "open_time" in df.columns:
        t_open = pd.DatetimeIndex(df["open_time"]).as_unit('ns').asi8
    else:
        t_open = pd.DatetimeIndex(df.index).as_unit('ns').asi8
    if "close_time" in df.columns:
        t_close = pd.DatetimeIndex(df["close_time"]).as_unit('ns').asi8
    else:  # M1
        t_close = t_open + 60 * 10**9
    g = lambda c: df[c].to_numpy(dtype=np.float64)
    if direction == 1:
        s = Series(t_open, t_close, g("bid_o"), g("bid_h"), g("bid_l"), g("bid_c"),
                   g("ask_o"), g("bid_o"), g("bid_h"), g("bid_l"), g("bid_c"))
    else:
        s = Series(t_open, t_close, -g("bid_o"), -g("bid_l"), -g("bid_h"), -g("bid_c"),
                   -g("bid_o"), -g("ask_o"), -g("ask_l"), -g("ask_h"), -g("ask_c"))
    if atr_n:
        s.atr = atr(s.h, s.l, s.c, atr_n)
    return s


class Market:
    def __init__(self, pair: str, bars: dict[str, pd.DataFrame], cfg: dict, direction: int):
        self.pair = pair
        self.direction = direction
        self.cfg = cfg
        fx = cfg["fixed_for_now"]
        n = fx["atr_period"]
        self.tf: dict[str, Series] = {}
        for name, df in bars.items():
            self.tf[name] = to_series(df, direction, atr_n=None if name == "M1" else n)
        k = fx["swing_k"]
        clear = fx["clear_break_atr"]
        self.state = {}
        for name, key in (("MN", "mn"), ("W", "w")):
            s = self.tf[name]
            self.state[name] = structure_state(s.h, s.l, s.c, k[key], clear, s.atr)
        self.pip = cfg["pip_size"][pair]

    def bias(self, t: int) -> tuple[int, int]:
        """(monthly, weekly) structure state from the last *closed* MN and W bars at time t."""
        out = []
        for name in ("MN", "W"):
            i = self.tf[name].idx_closed_by(t)
            out.append(int(self.state[name][i]) if i >= 0 else 0)
        return out[0], out[1]

    def atr_at(self, tfname: str, t: int) -> float:
        s = self.tf[tfname]
        i = s.idx_closed_by(t)
        return float(s.atr[i]) if i >= 0 else float("nan")


def setup_type(mn: int, w: int) -> str | None:
    """Setup type in direction space (+1 = with the trade)."""
    if mn == 0 or w == 0:
        return None  # neutral monthly or weekly: NO TRADE
    if mn == 1 and w == 1:
        return "continuation"
    if mn == -1 and w == -1:
        return "reversal_both"
    return "reversal_one"
