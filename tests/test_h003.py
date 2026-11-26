import numpy as np
import pandas as pd

from cjfx.h003 import engine as E


def _m1(days=5, start="2024-03-04 00:00"):
    # minute bars Sunday-evening-style continuous; price rises 1e-5 per minute
    idx = pd.date_range(start, periods=days * 1440, freq="1min", tz="UTC")
    px = 1.0 + np.arange(len(idx)) * 1e-5
    return pd.DataFrame({"bid_o": px, "bid_c": px + 1e-5}, index=idx)


def test_day_boundary_is_17_ny_with_dst():
    m1 = _m1(days=3, start="2024-03-06 00:00")   # US DST starts 10 Mar; here EST (UTC-5)
    d = E.daily_bars(m1, btc=True)
    # day 2024-03-07 ends at 17:00 NY = 22:00 UTC -> last bar 21:59 UTC
    last = m1.loc[:"2024-03-07 21:59"].iloc[-1]["bid_c"]
    assert np.isclose(d.loc["2024-03-07", "close"], last)
    m1s = _m1(days=3, start="2024-06-04 00:00")  # EDT (UTC-4): boundary 21:00 UTC
    ds = E.daily_bars(m1s, btc=True)
    assert np.isclose(ds.loc["2024-06-05", "close"], m1s.loc[:"2024-06-05 20:59"].iloc[-1]["bid_c"])


def test_exec_bar_is_03_ny():
    m1 = _m1(days=3, start="2024-06-04 00:00")
    d = E.daily_bars(m1, btc=True)
    # 03:00 EDT = 07:00 UTC on 2024-06-05
    assert np.isclose(d.loc["2024-06-05", "exec_px"], m1.loc["2024-06-05 07:00", "bid_o"])


def test_signal_blend_and_warmup():
    c = pd.Series(np.exp(np.linspace(0, 1, 400)))
    p = E.Params()
    s = E.signal(c, p)
    assert s.iloc[:252].isna().all() and (s.iloc[252:] == 1).all()


def test_band_rule():
    w = pd.Series([1.0, 1.1, 1.4, 1.3, -0.5])
    S = pd.Series([1, 1, 1, 1, -1.0])
    h = E.held_weights(w, S, 0.25)
    assert list(h) == [1.0, 1.0, 1.4, 1.4, -0.5]


def test_returns_timing_no_lookahead():
    idx = pd.bdate_range("2024-01-01", periods=5)
    days = pd.DataFrame({"close": [100, 110, 121, 121, 121.0], "exec_px": [100, 105, 115, 121, 121.0]}, index=idx)
    held = np.array([1.0, 1.0, 1.0, 0.0, 0.0])
    c = E.Costs(spread=np.zeros(5), slip_abs=0.0, swap_m=0.0, btc=True)
    r = E.daily_returns(days, held, c)
    # decided at close 0, enters at exec of day 1 (105) -> day 1 return = 110/105-1
    assert np.isclose(r["gross"].iloc[1], 110 / 105 - 1)
    assert np.isclose(r["gross"].iloc[2], 121 / 110 - 1)


def test_costs_and_swap():
    idx = pd.bdate_range("2024-01-01", periods=4)   # Mon..Thu
    days = pd.DataFrame({"close": [100.0] * 4, "exec_px": [100.0] * 4}, index=idx)
    held = np.array([2.0, 2.0, 2.0, 2.0])
    c = E.Costs(spread=np.full(4, 0.0002), slip_abs=0.01, swap_m=0.036, btc=False)
    r = E.daily_returns(days, held, c)
    assert np.isclose(r["tcost"].iloc[1], 2 * (0.0001 + 0.0001))
    assert np.isclose(r["swap"].iloc[2], 2 * 0.036 / 360)          # Wed day: prior Tue rollover
    assert np.isclose(r["swap"].iloc[3], 2 * 0.036 * 3 / 360)      # Thu row carries Wed triple


def test_nw_t_iid():
    rng = np.random.default_rng(0)
    x = rng.normal(0.1, 1, 20000)
    t, _ = E.nw_t(x, 5)
    assert 11 < t < 17


def test_bootstrap_mean_centered():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, 2000)
    m = E.stationary_bootstrap_means_fast(x, 300, 21, rng)
    assert abs(m.mean() - x.mean()) < 0.02 and 0.015 < m.std() < 0.035
