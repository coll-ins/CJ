"""Deterministic price-structure building blocks: ATR, swings, structure state."""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int) -> np.ndarray:
    """Wilder ATR. Value at i uses bars up to and including i (known at bar i close)."""
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    out = np.full(len(h), np.nan)
    if len(h) < n:
        return out
    out[n - 1] = tr[:n].mean()
    a = 1.0 / n
    for i in range(n, len(h)):
        out[i] = out[i - 1] + a * (tr[i] - out[i - 1])
    return out


def swing_highs(h: np.ndarray, k: int) -> np.ndarray:
    """Bar i is a swing high if its high is strictly above the k highs on each side.

    It is only *known* at the close of bar i + k (see confirm_index).
    """
    n = len(h)
    out = np.zeros(n, dtype=bool)
    if n < 2 * k + 1:
        return out
    w = sliding_window_view(h, 2 * k + 1)
    centre = w[:, k]
    others = np.delete(w, k, axis=1)
    out[k:n - k] = centre > others.max(axis=1)
    return out


def swing_lows(l: np.ndarray, k: int) -> np.ndarray:
    return swing_highs(-l, k)


def structure_state(h: np.ndarray, l: np.ndarray, c: np.ndarray, k: int, clear_atr: float, atr_arr: np.ndarray) -> np.ndarray:
    """Market structure after each bar's close: +1 bullish, -1 bearish, 0 neutral.

    Turns bullish on a close above the latest confirmed, not yet broken swing high, and
    bearish on a close below the latest confirmed swing low. If the breaking close is less
    than clear_atr * ATR beyond the swing, the state becomes neutral instead. The state
    then persists until the next break.
    """
    n = len(c)
    sh = swing_highs(h, k)
    sl = swing_lows(l, k)
    state = np.zeros(n, dtype=np.int8)
    cur = 0
    last_sh = np.nan
    last_sl = np.nan
    for j in range(n):
        # swings confirmed by the close of bar j-1 (index i = j-1-k) become usable at bar j
        i = j - 1 - k
        if i >= 0:
            if sh[i]:
                last_sh = h[i]
            if sl[i]:
                last_sl = l[i]
        a = atr_arr[j]
        if not np.isnan(last_sh) and c[j] > last_sh:
            cur = 1 if (not np.isnan(a) and c[j] - last_sh >= clear_atr * a) else 0
            last_sh = np.nan
        elif not np.isnan(last_sl) and c[j] < last_sl:
            cur = -1 if (not np.isnan(a) and last_sl - c[j] >= clear_atr * a) else 0
            last_sl = np.nan
        state[j] = cur
    return state


def last_confirmed_swing_high(h: np.ndarray, k: int) -> np.ndarray:
    """Level of the most recent swing high confirmed by the close of bar j-1, for each j."""
    n = len(h)
    sh = swing_highs(h, k)
    lvl = np.full(n, np.nan)
    conf = np.full(n, np.nan)
    idx = np.where(sh)[0]
    conf_at = idx + k + 1  # usable from bar i+k+1
    conf_at = conf_at[conf_at < n]
    conf[conf_at] = h[idx[: len(conf_at)]]
    # forward fill
    mask = ~np.isnan(conf)
    pos = np.where(mask, np.arange(n), 0)
    np.maximum.accumulate(pos, out=pos)
    lvl = np.where(mask[pos] | (pos > 0), conf[pos], np.nan)
    lvl[: (conf_at[0] if len(conf_at) else n)] = np.nan
    return lvl
