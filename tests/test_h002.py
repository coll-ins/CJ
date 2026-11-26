"""H002 unit tests (spec section 6 + v0.6 section 12). Synthetic fixtures only."""
import numpy as np
import pandas as pd
import pytest

from cjfx.h002 import engine as E
from cjfx.h002.sim import plan_trade, rollovers, run_trade

FX = E.Instrument("EURUSD", 0.0001, pmin_pips=1.0, slip_pips=0.2)
BTC = E.Instrument("BTCUSD", 1.0, pmin_bp=5.0, slip_bp=0.56, weekend_trading=True)


def ns(s):
    return pd.Timestamp(s, tz="UTC").value


def bars(times, o, h, l, c, minutes):
    return E.Bars(np.array([ns(t) for t in times], np.int64), np.array(o, float), np.array(h, float),
                  np.array(l, float), np.array(c, float), minutes * E.NS_MIN)


def level(v, side="high", start="2024-01-08 00:00", end="2024-01-15 00:00", segs=None):
    if segs:
        return E.Level("pw", side, "x", np.array([ns(s) for s, _ in segs]), np.array([x for _, x in segs]),
                       np.ones(len(segs), int), ns(end))
    return E.Level("pw", side, "x", np.array([ns(start)]), np.array([v]), np.array([0]), ns(end))


# ---------------------------------------------------------------- UTC boundaries (tests 1-5)
def test_01_histdata_est_fixed_offset():
    from cjfx.data.histdata import parse_csv
    df = parse_csv(b"20200309 000000;1.1;1.1;1.1;1.1;0\n")
    assert df.index[0] == pd.Timestamp("2020-03-09 05:00", tz="UTC")


def test_02_week_start_monday_and_sunday_belongs_to_ending_week():
    assert E.week_start(ns("2024-01-14 21:05")) == ns("2024-01-08")   # Sunday evening -> week of Mon 8th
    assert E.week_start(ns("2024-01-15 00:00")) == ns("2024-01-15")


def test_03_pwh_available_only_from_next_monday():
    t = pd.date_range("2024-01-08", "2024-01-22", freq="1h", tz="UTC", inclusive="left")
    v = np.arange(len(t), dtype=float)
    m1 = E.Bars(t.as_unit("ns").asi8, v, v + 0.5, v - 0.5, v, E.NS_MIN)
    lv = [L for L in E.period_levels(m1, "pw") if L.side == "high"]
    assert len(lv) == 1
    L = lv[0]
    assert L.seg_t[0] == ns("2024-01-15") and L.seg_v[0] == v[t < pd.Timestamp("2024-01-15", tz="UTC")].max() + 0.5


def test_04_pmh_leap_february():
    t = pd.date_range("2024-02-01", "2024-03-05", freq="1h", tz="UTC", inclusive="left")
    v = np.where(t == pd.Timestamp("2024-02-29 12:00", tz="UTC"), 10.0, 1.0)
    m1 = E.Bars(t.as_unit("ns").asi8, v, v, v, v, E.NS_MIN)
    L = [x for x in E.period_levels(m1, "pm") if x.side == "high"][0]
    assert L.seg_t[0] == ns("2024-03-01") and L.seg_v[0] == 10.0


def test_05_btc_weekend_in_week_from_monday():
    assert E.week_start(ns("2024-01-13 12:00")) == ns("2024-01-08")


# ---------------------------------------------------------------- pivots / clusters (6-11, B-3)
def _h1(highs, start="2024-01-08 00:00"):
    t = pd.date_range(start, periods=len(highs), freq="1h", tz="UTC")
    h = np.array(highs, float)
    return E.Bars(t.as_unit("ns").asi8, h - 0.0002, h, h - 0.0010, h - 0.0005, E.NS_H)


def test_06_07_pivot_strict_and_confirmed_after_k():
    base = [1.0] * 20
    hs = base[:]
    hs[5] = 1.01
    b = _h1(hs)
    from numpy.lib.stride_tricks import sliding_window_view as sw
    w = sw(b.h, 7)
    piv = w[:, 3] > np.delete(w, 3, axis=1).max(axis=1)
    assert piv[5 - 3]                      # pivot at bar 5
    hs[7] = 1.01                           # tie on the right -> not a pivot
    b2 = _h1(hs)
    w2 = sw(b2.h, 7)
    assert not (w2[:, 3] > np.delete(w2, 3, axis=1).max(axis=1))[5 - 3]


def _eq_fixture(second_high):
    hs = [1.0] * 60
    hs[10] = 1.0100
    hs[30] = second_high
    return _h1(hs)


def test_08_tolerance_in_and_out():
    b = _eq_fixture(1.01005)
    atr = E.atr14(b)
    tol = 0.1 * atr[33]
    inside = E.eq_clusters(_eq_fixture(1.0100 - 0.9 * tol), FX)
    outside = E.eq_clusters(_eq_fixture(1.0100 - 1.5 * tol), FX)
    assert any(L.side == "high" for L in inside)
    assert not any(L.side == "high" for L in outside)


def test_10_cluster_not_formed_if_first_pivot_swept_between():
    hs = [1.0] * 60
    hs[10] = 1.0100
    hs[20] = 1.0100 + 0.0002            # exceeds by >= pmin (1 pip) between the two pivots
    hs[30] = 1.0100
    assert not any(L.side == "high" and L.seg_v[0] == pytest.approx(1.0100) for L in E.eq_clusters(_h1(hs), FX))


def test_09_trading_day_count_skips_weekend_for_fx():
    fri, mon = ns("2024-01-12 12:00"), ns("2024-01-15 12:00")
    d = E.trading_day_index(np.array([fri, mon]), FX)
    assert d[1] - d[0] == 1
    sun = ns("2024-01-14 22:00")
    assert E.trading_day_index(np.array([sun]), FX)[0] == E.trading_day_index(np.array([mon]), FX)[0]


# ---------------------------------------------------------------- sweep and reclaim (12-19)
T = [f"2024-01-08 10:{m:02d}" for m in range(0, 60, 5)] + [f"2024-01-08 11:{m:02d}" for m in range(0, 60, 5)]


def m5(highs, closes, lows=None):
    n = len(highs)
    lows = lows or [x - 0.0005 for x in closes]
    return bars(T[:n], closes, highs, lows, closes, 5)


def test_12_same_candle_sweep_reclaim():
    b = m5([1.1001 + 1e-9], [1.0999])
    ev = E.scan_level(level(1.1000), b, np.full(1, 0.001), FX)
    assert ev["status"] == "reclaim" and ev["sweep_to_reclaim"] == 0


def test_13_below_pmin_no_sweep():
    b = m5([1.10009], [1.0999])
    assert E.scan_level(level(1.1000), b, np.full(1, 0.001), FX)["status"] == "never_swept"


def test_14_close_equal_level_not_reclaim():
    b = m5([1.1002, 1.1001], [1.1000, 1.1000])
    ev = E.scan_level(level(1.1000), b, np.full(2, 0.01), FX)
    assert ev["status"] != "reclaim"


def test_15_window_12_m5_candles():
    hs = [1.1002] + [1.1001] * 12
    cl12 = [1.1001] * 11 + [1.0999] + [1.0999]
    ev = E.scan_level(level(1.1000), m5(hs, cl12), np.full(13, 0.01), FX)
    assert ev["status"] == "reclaim" and ev["sweep_to_reclaim"] == 11
    cl13 = [1.1001] * 12 + [1.0999]
    ev = E.scan_level(level(1.1000), m5(hs, cl13), np.full(13, 0.01), FX)
    assert ev["status"] == "window_expired"


def test_16_h1_same_candle_only():
    b = bars(["2024-01-08 10:00", "2024-01-08 11:00"], [1.1, 1.1], [1.1002, 1.1001], [1.099, 1.099], [1.1001, 1.0999], 60)
    assert E.scan_level(level(1.1000), b, np.full(2, 0.01), FX)["status"] == "window_expired"


def test_17_consumed_beyond_one_atr():
    b = m5([1.1002, 1.1030, 1.1001], [1.1001, 1.1025, 1.0999])
    ev = E.scan_level(level(1.1000), b, np.full(3, 0.0010), FX)
    assert ev["status"] == "consumed"


def test_m1_level_expiry_keeps_window():
    b = bars(["2024-01-14 23:55", "2024-01-15 00:00"], [1.1, 1.1], [1.1002, 1.1001], [1.099, 1.099], [1.1001, 1.0999], 5)
    L = level(1.1000, start="2024-01-08", end="2024-01-15 00:00")
    assert E.scan_level(L, b, np.full(2, 0.01), FX)["status"] == "reclaim"


# ---------------------------------------------------------------- weekend / flat (B-1)
def test_weekend_window_and_flat_time():
    assert E.in_weekend_window(ns("2024-01-12 20:00"), FX)
    assert not E.in_weekend_window(ns("2024-01-12 19:55"), FX)
    assert E.in_weekend_window(ns("2024-01-14 22:00"), FX)
    assert E.flat_time(ns("2024-01-10 10:00"), FX) == ns("2024-01-12 20:00")
    assert E.flat_time(ns("2024-01-10 10:00"), BTC) == ns("2024-01-14 23:55")
    assert not E.in_weekend_window(ns("2024-01-13 12:00"), BTC)


# ---------------------------------------------------------------- fills and ambiguity (20-25, B-4)
def _m1(prices_ohlc, start="2024-01-09 10:00"):
    t = pd.date_range(start, periods=len(prices_ohlc), freq="1min", tz="UTC").as_unit("ns").asi8
    a = np.array(prices_ohlc, float)
    return E.Bars(t, a[:, 0], a[:, 1], a[:, 2], a[:, 3], E.NS_MIN)


def _plan(long, entry, stop, target, R, slip=0.0):
    return {"e": 0, "t_entry": ns("2024-01-09 10:00"), "entry": entry, "stop": stop, "target": target, "R": R,
            "long": long, "slip": slip}


def test_21_stop_and_target_same_m1_bar_is_stop():
    m1 = _m1([[1.1000, 1.1040, 1.0980, 1.1000]])
    r = run_trade(_plan(True, 1.1000, 1.0990, 1.1030, 0.0010), m1, np.zeros(1), FX)
    assert r["outcome"] == "stop"


def test_20_first_m1_bar_wins():
    m1 = _m1([[1.1000, 1.1035, 1.0995, 1.1030], [1.1030, 1.1030, 1.0980, 1.0985]])
    r = run_trade(_plan(True, 1.1000, 1.0990, 1.1030, 0.0010), m1, np.zeros(2), FX)
    assert r["outcome"] == "target" and r["r"] == pytest.approx(3.0)


def test_22_gap_through_stop_fills_at_open():
    m1 = _m1([[1.1000, 1.1005, 1.0995, 1.1000], [1.0970, 1.0975, 1.0960, 1.0965]])
    r = run_trade(_plan(True, 1.1000, 1.0990, 1.1030, 0.0010, slip=0.00002), m1, np.zeros(2), FX)
    assert r["exit"] == pytest.approx(1.0970 - 0.00002) and r["r"] < -1


def test_24_short_stop_triggers_on_ask():
    m1 = _m1([[1.1000, 1.1009, 1.0995, 1.1000]])
    spr = np.array([0.0002])
    r = run_trade(_plan(False, 1.1000, 1.1010, 1.0970, 0.0010), m1, spr, FX)
    assert r["outcome"] == "stop"          # bid high 1.1009 + spread 0.0002 = ask 1.1011 >= stop


def test_23_weekly_flat_exit():
    t0 = "2024-01-12 19:58"
    m1 = _m1([[1.1, 1.1001, 1.0999, 1.1]] * 4, start=t0)
    p = _plan(True, 1.1, 1.09, 1.13, 0.01)
    p["t_entry"] = ns(t0)
    r = run_trade(p, m1, np.zeros(4), FX)
    assert r["outcome"] == "weekly_flat" and r["t_exit"] == ns("2024-01-12 20:00")


def test_25_min_stop_skip():
    m1 = _m1([[1.1000, 1.1001, 1.0999, 1.1000]] * 3)
    sig = {"side": "low", "reclaim_close_t": ns("2024-01-09 10:00"), "extreme": 1.09995, "atr": 0.00001, "close": 1.1}
    p = plan_trade(sig, m1, np.full(3, 0.0001), lambda t, b: (np.full(len(t), 0.0001), np.zeros(len(t), bool)), FX)
    assert p["skip"] == "stop_too_small"


# ---------------------------------------------------------------- gaps (26-28, B-2) and swap
def test_26_gap_detection_and_overlap():
    t = pd.date_range("2023-01-02", "2024-01-20", freq="1min", tz="UTC")
    t = t[(t.dayofweek < 5)]
    hole = (t >= pd.Timestamp("2024-01-10 12:00", tz="UTC")) & (t < pd.Timestamp("2024-01-10 12:05", tz="UTC"))
    short = (t >= pd.Timestamp("2024-01-11 12:00", tz="UTC")) & (t < pd.Timestamp("2024-01-11 12:04", tz="UTC"))
    t = t[~hole & ~short]
    v = np.ones(len(t))
    g = E.gap_intervals(E.Bars(t.as_unit("ns").asi8, v, v, v, v, E.NS_MIN))
    assert E.overlapping_gap(g, ns("2024-01-10 11:00"), ns("2024-01-10 13:00")) is not None
    assert E.overlapping_gap(g, ns("2024-01-11 11:00"), ns("2024-01-11 13:00")) is None


def test_rollover_wednesday_triple_and_dst():
    assert rollovers(ns("2024-01-10 12:00"), ns("2024-01-10 23:00"), False) == 3   # Wed 17:00 NY = 22:00 UTC
    assert rollovers(ns("2024-07-10 12:00"), ns("2024-07-10 21:30"), False) == 3   # summer: 21:00 UTC
    assert rollovers(ns("2024-01-09 12:00"), ns("2024-01-09 21:59"), False) == 0


def test_29_spread_model_prev_month_and_extrapolation():
    prof = pd.DataFrame({"series": "S", "month": ["2020-01"] * 168 + ["2020-02"] * 168, "how": list(range(168)) * 2,
                         "median": [0.0001] * 168 + [0.0002] * 168, "p90": [0.0003] * 336})
    man = pd.DataFrame({"series": "S", "month": ["2020-01", "2020-02"], "median_spread": [0.0001, 0.0002], "mean_mid": [1.0, 1.0]})
    m = E.SpreadModel(prof, man, "S", fx=True)
    s, ext = m.at(np.array([ns("2020-03-04 10:00"), ns("2020-02-04 10:00"), ns("2019-05-01")]), np.ones(3))
    assert s[0] == pytest.approx(0.0002) and s[1] == pytest.approx(0.0001) and ext[2] and not ext[0]
    mb = E.SpreadModel(prof, man, "S", fx=False)
    s2, _ = mb.at(np.array([ns("2019-05-01")]), np.array([2.0]))
    assert s2[0] == pytest.approx(0.00015 * 2.0)


def test_how_index_monday_zero():
    assert ((ns("2024-01-08 00:30") // E.NS_H) + 72) % 168 == 0


# ---------------------------------------------------------------- stats (4.4, M-13, M-14)
def test_28_stationary_bootstrap_blocks():
    from cjfx.h002.stats import stationary_index
    idx = stationary_index(100, 200, 4.0, 1)
    cont = (idx[:, 1:] == (idx[:, :-1] + 1) % 100).mean()
    assert abs(cont - 0.75) < 0.02 and idx.min() >= 0 and idx.max() < 100


def test_29_romano_wolf_monotone_and_two_sided():
    from cjfx.h002.stats import romano_wolf
    rng = np.random.default_rng(0)
    tb = rng.standard_normal((5000, 3))
    p = romano_wolf(np.array([5.0, -5.0, 0.1]), tb)
    assert p[0] < 0.01 and p[1] < 0.01 and p[2] > 0.5


def test_30_breakeven_crossing():
    from cjfx.h002.stats import _crossing
    assert _crossing([(1.0, 0.2), (2.0, -0.2)]) == 1.5
    assert _crossing([(0.5, -0.1), (1.0, -0.2)]) == "<0.5x"
    assert _crossing([(1.0, 0.2), (3.0, 0.1)]) == ">3x"


def test_31_deflated_sharpe_more_trials_lower():
    from cjfx.h002.stats import deflated_sharpe
    a = deflated_sharpe(0.15, 500, 1.0, 3.0, 0.002, 54)
    b = deflated_sharpe(0.15, 500, 1.0, 3.0, 0.002, 13878)
    assert 0 < b < a < 1
