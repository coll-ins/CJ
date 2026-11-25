"""H4 supply/demand zones (written for demand; supply = demand in short space)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .indicators import last_confirmed_swing_high
from .market import Series

INF = np.iinfo(np.int64).max


@dataclass
class Zone:
    zid: int
    base: tuple
    top: float
    bottom: float
    created_idx: int     # H4 index of the impulse-completing bar
    created_time: int    # its close time: the zone exists from here
    dead_time: int       # H4 close below bottom, or expiry by age (touch expiry is handled in the scan)


def find_zones(h4: Series, fx: dict, base_mode: str) -> list[Zone]:
    n = len(h4)
    o, h, l, c, a = h4.o, h4.h, h4.l, h4.c, h4.atr
    bear = c < o
    bull = c > o
    nb = fx["zone_base_candles"]
    lookback = fx["nearest_3_max_lookback_h4_bars"]
    window = fx["impulse_window_h4_bars"]
    imp = fx["impulse_atr_h4"]
    expiry = fx["zone_expiry_h4_bars"]
    last_sh = last_confirmed_swing_high(h, fx["swing_k"]["h4"])
    zones: list[Zone] = []
    bear_idx = np.where(bear)[0]
    for b in bear_idx:
        if b + 1 >= n or not bull[b + 1] or np.isnan(a[b]):
            continue
        if base_mode == "consecutive_3":
            if b - (nb - 1) < 0 or not bear[b - (nb - 1): b + 1].all():
                continue
            base = tuple(range(b - nb + 1, b + 1))
        elif base_mode == "nearest_3":
            p = np.searchsorted(bear_idx, b, side="right")
            cand = bear_idx[max(0, p - nb): p]
            if len(cand) < nb or b - cand[0] > lookback:
                continue
            base = tuple(int(x) for x in cand)
        else:
            raise ValueError(base_mode)
        top = float(h[list(base)].max())
        bottom = float(l[list(base)].min())
        for j in range(b + 1, min(n, b + 1 + window)):
            if c[j] < bottom:
                break
            if c[j] >= top + imp * a[b] and not np.isnan(last_sh[j]) and c[j] > last_sh[j]:
                after = np.where(c[j + 1:] < bottom)[0]
                dead = h4.t_close[j + 1 + after[0]] if len(after) else INF
                if j + expiry < n:
                    dead = min(dead, h4.t_close[j + expiry])
                zones.append(Zone(len(zones), base, top, bottom, j, int(h4.t_close[j]), int(dead)))
                break
    return zones
