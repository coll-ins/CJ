"""H002 engine (spec v0.6, frozen 4c9b460): levels, sweep/reclaim, trade simulation.

All prices are bid unless named ask. Times are int64 nanoseconds UTC. Nothing here reads
outcomes to set a rule; every number comes from config/h002.yaml or the spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..indicators import atr as wilder_atr

NS_MIN = 60_000_000_000
NS_H = 60 * NS_MIN
NS_D = 24 * NS_H
TF_MIN = {"M5": 5, "M15": 15, "H1": 60}
NY = "America/New_York"


# ----------------------------------------------------------------------------- instruments
@dataclass
class Instrument:
    name: str
    pip: float
    pmin_pips: float | None = None   # FX
    pmin_bp: float | None = None     # others, bp of level price
    slip_pips: float | None = None   # FX
    slip_bp: float | None = None     # others (v0.6 M-10)
    weekend_trading: bool = False    # BTC

    def pmin(self, level: float) -> float:
        return self.pmin_pips * self.pip if self.pmin_pips is not None else self.pmin_bp * 1e-4 * level

    def slip(self, price: float) -> float:
        return self.slip_pips * self.pip if self.slip_pips is not None else self.slip_bp * 1e-4 * price


def instruments_from_config(cfg: dict) -> dict[str, Instrument]:
    out = {}
    pm = cfg["sweep"]["p_min"]
    slip_bp = cfg["v06"]["slippage_bp"]
    for name in cfg["instruments"]:
        p = pm[name]
        out[name] = Instrument(
            name=name, pip=cfg["pip_size"][name],
            pmin_pips=p.get("pips"), pmin_bp=p.get("bp"),
            slip_pips=None if name in slip_bp else cfg["costs"]["slippage_per_side"][name],
            slip_bp=slip_bp.get(name), weekend_trading=(name == "BTCUSD"))
    return out


# ----------------------------------------------------------------------------- bars
@dataclass
class Bars:
    t: np.ndarray   # open time ns
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    tf_ns: int

    @property
    def tc(self) -> np.ndarray:
        return self.t + self.tf_ns


def m1_arrays(m1: pd.DataFrame) -> Bars:
    return Bars(m1.index.as_unit("ns").asi8.astype(np.int64),
                m1["bid_o"].to_numpy(float), m1["bid_h"].to_numpy(float), m1["bid_l"].to_numpy(float),
                m1["bid_c"].to_numpy(float), NS_MIN)


def resample(m1: Bars, minutes: int) -> Bars:
    """UTC clock-aligned bars from existing M1 minutes only (empty periods produce no bar)."""
    step = minutes * NS_MIN
    key = (m1.t // step) * step
    starts = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
    ends = np.r_[starts[1:], len(key)]
    return Bars(key[starts], m1.o[starts], np.maximum.reduceat(m1.h, starts), np.minimum.reduceat(m1.l, starts),
                m1.c[ends - 1], step)


def atr14(b: Bars) -> np.ndarray:
    """Wilder ATR14 on existing bars; value at i known at close of bar i (v0.6 M-5)."""
    return wilder_atr(b.h, b.l, b.c, 14)


# ----------------------------------------------------------------------------- calendar
def week_start(ns: np.ndarray | int) -> np.ndarray:
    """Monday 00:00 UTC of the week containing ns (1970-01-01 was a Thursday)."""
    days = np.asarray(ns) // NS_D
    return (days - (days + 3) % 7) * NS_D


def month_start(ns: np.ndarray) -> np.ndarray:
    d = pd.to_datetime(np.asarray(ns), utc=True)
    return pd.to_datetime({"year": d.year, "month": d.month, "day": 1}).dt.tz_localize("UTC").values.astype("datetime64[ns]").astype(np.int64)


def in_weekend_window(ns: np.ndarray | int, inst: Instrument) -> np.ndarray:
    """FX/gold/NAS100: Fri 20:00 UTC to Mon 00:00 UTC. BTC: never (it is flattened Sun 23:55)."""
    ns = np.asarray(ns)
    if inst.weekend_trading:
        return np.zeros(ns.shape, bool)
    return (ns - week_start(ns)) >= (4 * NS_D + 20 * NS_H)


def flat_time(ns: int, inst: Instrument) -> int:
    """Next weekly flat time at or after ns (v0.6 B-1)."""
    ws = int(week_start(ns))
    f = ws + (6 * NS_D + 23 * NS_H + 55 * NS_MIN if inst.weekend_trading else 4 * NS_D + 20 * NS_H)
    return f if f > ns else f + 7 * NS_D


# ----------------------------------------------------------------------------- data gaps (v0.6 B-2)
def gap_intervals(m1: Bars, min_missing: int = 5, share: float = 0.5) -> np.ndarray:
    """[start, end) ns of runs >= min_missing consecutive missing minutes inside normal hours.

    Normal hours for year Y = New York minute-of-week with a bar in >= share of the weeks of
    year Y-1 (first year uses itself). Strictly prior data, DST-correct.
    """
    t0 = (m1.t[0] // NS_D) * NS_D
    grid = np.arange(t0, m1.t[-1] + NS_MIN, NS_MIN)
    have = np.zeros(len(grid), bool)
    have[((m1.t - t0) // NS_MIN).astype(np.int64)] = True
    ny = pd.DatetimeIndex(grid.astype("datetime64[ns]"), tz="UTC").tz_convert(NY)
    mow = (ny.dayofweek * 1440 + ny.hour * 60 + ny.minute).to_numpy()
    year = ny.year.to_numpy()
    wk = week_start(grid)
    normal = np.zeros(len(grid), bool)
    years = np.unique(year)
    tables = {}
    for y in years:
        sel = year == y
        nweeks = len(np.unique(wk[sel]))
        cnt = np.bincount(mow[sel & have], minlength=7 * 1440)
        tables[y] = cnt / max(nweeks, 1) >= share
    for y in years:
        src = tables.get(y - 1, tables[y])
        sel = year == y
        normal[sel] = src[mow[sel]]
    miss = normal & ~have
    d = np.diff(np.r_[0, miss.astype(np.int8), 0])
    s, e = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    keep = (e - s) >= min_missing
    return np.c_[grid[s[keep]], grid[e[keep] - 1] + NS_MIN] if keep.any() else np.zeros((0, 2), np.int64)


def overlapping_gap(gaps: np.ndarray, a: int, b: int) -> int | None:
    """End time of the first gap overlapping [a, b], else None."""
    if not len(gaps):
        return None
    i = np.searchsorted(gaps[:, 1], a, side="right")
    if i < len(gaps) and gaps[i, 0] <= b:
        return int(gaps[i, 1])
    return None


# ----------------------------------------------------------------------------- spreads (3.4 + v0.6 M-7, M-9)
class SpreadModel:
    """Spread in price units at a time, from the Exness archive (previous month's hour-of-week bucket)."""

    def __init__(self, profiles: pd.DataFrame, manifest: pd.DataFrame, series: str, fx: bool,
                 stat: str = "median", mult: float = 1.0):
        p = profiles[profiles.series == series]
        man = manifest[manifest.series == series].sort_values("month")
        self.months = {}
        for mth, g in p.groupby("month"):
            arr = np.full(168, np.nan)
            arr[g["how"].to_numpy(int)] = g[stat].to_numpy(float)
            fill = float(man.loc[man.month == mth, "median_spread"].iloc[0])
            self.months[mth] = np.where(np.isnan(arr), fill, arr)
        first12 = list(man.month)[:12]
        stack = np.vstack([self.months[m] for m in first12])
        self.pre = np.nanmedian(stack, axis=0)
        self.pre_mid = float(man[man.month.isin(first12)].mean_mid.mean())
        self.fx = fx
        self.first_month = man.month.iloc[0]
        self.mult = mult

    @staticmethod
    def _prev_month(ns: np.ndarray) -> np.ndarray:
        d = pd.DatetimeIndex(np.asarray(ns).astype("datetime64[ns]"), tz="UTC")
        y, m = d.year.to_numpy(), d.month.to_numpy()
        py, pm = np.where(m == 1, y - 1, y), np.where(m == 1, 12, m - 1)
        return np.char.add(np.char.add(py.astype(str), "-"), np.char.zfill(pm.astype(str), 2))

    def at(self, ns: np.ndarray, bid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(spread, extrapolated flag) for arrays of times and bid prices."""
        ns = np.asarray(ns)
        how = ((ns // NS_H) + 72) % 168          # 1970-01-01 00:00 was Thursday -> hour 72 of week
        pm = self._prev_month(ns)
        out = np.empty(len(ns))
        ext = np.zeros(len(ns), bool)
        for mth in np.unique(pm):
            sel = pm == mth
            if mth in self.months:
                out[sel] = self.months[mth][how[sel]]
            else:
                ext[sel] = True
                base = self.pre[how[sel]]
                out[sel] = base if self.fx else base / self.pre_mid * bid[sel]
        return out * self.mult, ext


# ----------------------------------------------------------------------------- levels
@dataclass
class Level:
    source: str              # pw, pm, eq, or placebo tags
    side: str                # "high" (bearish setup) or "low" (bullish)
    lid: str
    seg_t: np.ndarray        # segment start times (ns); level valid from seg_t[i] to seg_t[i+1]
    seg_v: np.ndarray        # level value per segment
    seg_n: np.ndarray        # touches (pivots) per segment
    t_end: int               # expiry (ns); a sweep before t_end keeps its window (v0.6 M-1)
    meta: dict = field(default_factory=dict)


def period_levels(m1: Bars, kind: str) -> list[Level]:
    """Previous completed week (Mon 00:00 UTC) or month high/low; usable from the next period start."""
    if kind == "pw":
        key = week_start(m1.t)
    else:
        key = month_start(m1.t)
    starts = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
    keys = key[starts]
    hi = np.maximum.reduceat(m1.h, starts)
    lo = np.minimum.reduceat(m1.l, starts)
    out = []
    for i in range(len(keys) - 1):
        a, b = int(keys[i + 1]), (int(keys[i + 2]) if i + 2 < len(keys) else int(keys[i + 1]) + 40 * NS_D)
        # the previous period must be the immediately preceding calendar period
        if kind == "pw" and keys[i + 1] - keys[i] != 7 * NS_D:
            continue
        if kind == "pw":
            b = a + 7 * NS_D
        else:
            nxt = pd.Timestamp(a, tz="UTC") + pd.offsets.MonthBegin(1)
            prev_expected = pd.Timestamp(a, tz="UTC") - pd.offsets.MonthBegin(1)
            if prev_expected.value != keys[i]:
                continue
            b = nxt.value
        for side, v in (("high", hi[i]), ("low", lo[i])):
            out.append(Level(kind, side, f"{kind}:{side}:{a}", np.array([a]), np.array([v]), np.array([0]), b,
                             {"range_hi": hi[i], "range_lo": lo[i]}))
    return out


def trading_day_index(ns: np.ndarray, inst: Instrument) -> np.ndarray:
    """Trading-day counter: BTC = calendar days; others = Mon-Fri UTC days, Sunday counted as Monday."""
    days = np.asarray(ns) // NS_D
    if inst.weekend_trading:
        return days
    dow = (days + 3) % 7                     # 0 = Monday
    week = (days - dow) // 7
    d = np.where(dow == 6, 0, np.minimum(dow, 4))   # Sunday -> next week's Monday; Saturday -> Friday
    week = np.where(dow == 6, week + 1, week)
    return week * 5 + d


def eq_clusters(h1: Bars, inst: Instrument, k: int = 3, tol_atr: float = 0.10, max_span: int = 5,
                life: int = 5, unequal_placebo: bool = False) -> list[Level]:
    """EQH/EQL clusters per spec 2.2 + v0.6 B-3. With unequal_placebo, returns single pivots that
    are not in any cluster at their confirmation time (v0.6 M-16)."""
    a = atr14(h1)
    out = []
    tdi_all = trading_day_index(h1.t, inst)
    for side in ("high", "low"):
        px = h1.h if side == "high" else -h1.l     # work on 'highs' of the mirrored series
        n = len(px)
        piv = np.zeros(n, bool)
        if n > 2 * k:
            from numpy.lib.stride_tricks import sliding_window_view as sw
            w = sw(px, 2 * k + 1)
            piv[k:n - k] = w[:, k] > np.delete(w, k, axis=1).max(axis=1)
        idx = np.flatnonzero(piv)
        # running max for 'no high between Q and P exceeded level + pmin' checks
        active: list[dict] = []     # clusters: level (mirrored), members idx, segs, swept flag
        singles: list[int] = []
        for i in idx:
            conf = i + k                               # known at close of bar i+k
            tconf = int(h1.t[conf] + h1.tf_ns)
            p = px[i]
            lvl_real = lambda v: v if side == "high" else -v
            pm = inst.pmin(abs(p))
            tol = tol_atr * a[conf] if np.isfinite(a[conf]) else np.nan
            # retire clusters swept (any H1 high >= level + pmin after its last update) or expired
            for C in active:
                if C["dead"]:
                    continue
                last = C["upd_bar"]
                seg = px[last + 1: conf + 1]
                if len(seg) and seg.max() >= C["lvl"] + inst.pmin(abs(C["lvl"])):
                    C["dead"] = True
                elif tconf >= C["t_end"]:
                    C["dead"] = True
            joined = False
            if np.isfinite(tol):
                live = [C for C in active if not C["dead"]]
                if live:
                    C = live[-1]                        # most recent cluster (A-5)
                    span = tdi_all[i] - tdi_all[C["members"][0]]
                    if abs(p - C["lvl"]) <= tol and p < C["lvl"] + inst.pmin(abs(C["lvl"])) and span <= max_span:
                        C["members"].append(i)
                        if p > C["lvl"]:
                            C["lvl"] = p
                        C["segs"].append((tconf, C["lvl"], len(C["members"])))
                        C["upd_bar"] = conf
                        C["t_end"] = _eq_expiry(h1.t[i], inst, life)
                        joined = True
                if not joined:
                    for qi in range(len(singles) - 1, -1, -1):
                        q = singles[qi]
                        if tdi_all[i] - tdi_all[q] > max_span:
                            break
                        lvl = max(p, px[q])
                        between = px[q + 1:i]
                        if abs(p - px[q]) <= tol and (not len(between) or between.max() < lvl + inst.pmin(abs(lvl))):
                            C = {"lvl": lvl, "members": [q, i], "segs": [(tconf, lvl, 2)], "upd_bar": conf,
                                 "t_end": _eq_expiry(h1.t[i], inst, life), "dead": False, "t0": tconf}
                            active.append(C)
                            singles.pop(qi)
                            joined = True
                            break
            if not joined:
                singles.append(i)
                if unequal_placebo:
                    out.append(Level("eq_unequal", side, f"equ:{side}:{tconf}", np.array([tconf]),
                                     np.array([lvl_real(p)]), np.array([1]),
                                     _eq_expiry(h1.t[i], inst, life)))
        if not unequal_placebo:
            for C in active:
                st = np.array([s[0] for s in C["segs"]], np.int64)
                v = np.array([s[1] for s in C["segs"]])
                nn = np.array([s[2] for s in C["segs"]])
                out.append(Level("eq", side, f"eq:{side}:{C['t0']}", st, v if side == "high" else -v, nn, int(C["t_end"])))
    return out


def _eq_expiry(t_pivot: int, inst: Instrument, life: int) -> int:
    """00:00 UTC after the 5th trading day after the newest pivot's trading day."""
    d = int(t_pivot // NS_D)
    if inst.weekend_trading:
        return (d + life + 1) * NS_D
    target = int(trading_day_index(np.array([t_pivot]), inst)[0]) + life
    while True:
        d += 1
        dow = (d + 3) % 7
        if dow in (5, 6):
            continue
        if int(trading_day_index(np.array([d * NS_D]), inst)[0]) > target:
            return d * NS_D


# ----------------------------------------------------------------------------- sweep / reclaim (3.2)
def scan_level(L: Level, b: Bars, atr_tf: np.ndarray, inst: Instrument, window_ns: int = 60 * NS_MIN,
               max_pen_atr: float = 1.0) -> dict | None:
    """Run the state machine for one level on one confirmation TF. Returns an event dict or None."""
    hi = L.side == "high"
    t0, t1 = int(L.seg_t[0]), L.t_end
    i0, i1 = np.searchsorted(b.t, t0, "left"), np.searchsorted(b.t, t1, "left")
    if i0 >= i1:
        return None
    # level per candle (segments)
    seg_idx = np.searchsorted(L.seg_t, b.t[i0:i1], "right") - 1
    lv = L.seg_v[seg_idx]
    pm = np.array([inst.pmin(abs(v)) for v in L.seg_v])[seg_idx]
    hit = (b.h[i0:i1] >= lv + pm) if hi else (b.l[i0:i1] <= lv - pm)
    if not hit.any():
        return {"status": "never_swept"}
    j = i0 + int(np.argmax(hit))
    level = float(lv[j - i0])
    touches = int(L.seg_n[seg_idx[j - i0]])
    deadline = int(b.t[j]) + window_ns
    extreme = b.h[j] if hi else b.l[j]
    ev = {"lid": L.lid, "source": L.source, "side": L.side, "level": level, "touches": touches,
          "sweep_t": int(b.t[j]), "sweep_i": j}
    c = j
    while c < len(b.t) and b.t[c] < deadline:
        extreme = max(extreme, b.h[c]) if hi else min(extreme, b.l[c])
        close = b.c[c]
        if (close < level) if hi else (close > level):
            ev.update(status="reclaim", reclaim_i=c, reclaim_close_t=int(b.t[c] + b.tf_ns), extreme=float(extreme),
                      atr=float(atr_tf[c]), close=float(close), open_=float(b.o[c]),
                      rng=float(b.h[c] - b.l[c]), sweep_to_reclaim=c - j)
            return ev
        prev_atr = atr_tf[c - 1] if c > 0 else np.nan
        if np.isfinite(prev_atr) and ((close > level + max_pen_atr * prev_atr) if hi else (close < level - max_pen_atr * prev_atr)):
            ev.update(status="consumed", extreme=float(extreme))
            return ev
        c += 1
    ev.update(status="window_expired", extreme=float(extreme))
    return ev
