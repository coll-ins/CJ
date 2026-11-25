import numpy as np
import pandas as pd
import pytest

from cjfx.engine import ExecContext, Setup
from cjfx.market import Market
from cjfx.sim import forced_exit_time, simulate


class FakeMkt:
    pass


def make(cfg, mids, start="2023-07-12 08:00", spread=0.0, wick=0.0, flat=False):
    idx = pd.date_range(start, periods=len(mids), freq="1min", tz="UTC")
    mids = np.asarray(mids, float)
    o = mids.copy() if flat else np.r_[mids[0], mids[:-1]]
    df = pd.DataFrame({"bid_o": o, "bid_h": np.maximum(o, mids) + wick, "bid_l": np.minimum(o, mids) - wick, "bid_c": mids}, index=idx)
    for s in "ohlc":
        df[f"ask_{s}"] = df[f"bid_{s}"] + spread
    bars = {"M1": df, "M5": df.assign(open_time=idx, close_time=idx + pd.Timedelta(minutes=1)), "H1": df, "H4": df, "D": df.iloc[:30], "W": df.iloc[:30], "MN": df.iloc[:30]}
    m = Market("EURUSD", bars, cfg, 1)
    return m


def setup_at(m, t, sweep_low, execution="swing_h1"):
    return Setup("EURUSD", 1, execution, 0, 1.0, 0.9, t, t, 1.0, sweep_low, t, t, 0, 1.2, sweep_low,
                 atr_h1=0.001, atr_h4=0.01, bias_mn=1, bias_w=1, setup_type="continuation")


def _cfg(cfg):
    c = dict(cfg)
    c["costs"] = dict(cfg["costs"], slippage_pips_per_side=0.0)
    return c


def test_fixed_target_hit(cfg):
    c = _cfg(cfg)
    path = [1.1000] * 3 + list(np.linspace(1.1000, 1.1100, 50))
    m = make(c, path)
    st = setup_at(m, int(m.tf["M1"].t_open[1]), sweep_low=1.0980 + 0.0001)  # stop = 1.0981 - 0.0001 buffer = 1.0980
    ctx = ExecContext(m.tf["M5"], 3)
    tr = simulate(st, "sweep_wick", "fixed_3r", m, ctx, [], c)
    assert tr.exit_reason == "target"
    assert tr.r_dist == pytest.approx(0.0020)
    assert tr.r_mult == pytest.approx(3.0)


def test_same_bar_stop_wins(cfg):
    c = _cfg(cfg)
    m = make(c, [1.1000] * 5 + [1.1000] * 5, wick=0.0100)  # every bar spans both stop and target
    st = setup_at(m, int(m.tf["M1"].t_open[1]), sweep_low=1.0981)
    tr = simulate(st, "sweep_wick", "fixed_3r", m, ExecContext(m.tf["M5"], 3), [], c)
    assert tr.exit_reason == "stop"
    assert tr.r_mult == pytest.approx(-1.0)


def test_gap_through_stop_fills_at_open(cfg):
    c = _cfg(cfg)
    m = make(c, [1.1000] * 3 + [1.0950] * 3, flat=True)  # bar 3 opens 50 pips lower
    st = setup_at(m, int(m.tf["M1"].t_open[1]), sweep_low=1.0981)
    tr = simulate(st, "sweep_wick", "fixed_3r", m, ExecContext(m.tf["M5"], 3), [], c)
    assert tr.r_mult == pytest.approx((1.0950 - 1.1000) / 0.0020)


def test_spread_costs_on_entry(cfg):
    c = _cfg(cfg)
    m = make(c, [1.1000] * 3 + [1.0950] * 3, spread=0.0001)
    st = setup_at(m, int(m.tf["M1"].t_open[1]), sweep_low=1.0981)
    tr = simulate(st, "sweep_wick", "fixed_3r", m, ExecContext(m.tf["M5"], 3), [], c)
    assert tr.entry == pytest.approx(1.1001)


def test_intraday_forced_exit_before_ny_close(cfg):
    c = _cfg(cfg)
    m = make(c, [1.1000] * 900, start="2023-07-12 08:00")  # flat until after 21:00 UTC
    t_in = int(m.tf["M1"].t_open[10])
    assert pd.Timestamp(forced_exit_time(t_in, c), tz="UTC") == pd.Timestamp("2023-07-12 20:55", tz="UTC")
    st = setup_at(m, t_in, sweep_low=1.0981, execution="intraday_m5")
    tr = simulate(st, "sweep_wick", "fixed_3r", m, ExecContext(m.tf["M5"], 3), [], c)
    assert tr.exit_reason == "time_exit"
    assert pd.Timestamp(tr.exit_time, tz="UTC") == pd.Timestamp("2023-07-12 20:55", tz="UTC")


def test_trailing_locks_2r(cfg):
    c = _cfg(cfg)
    path = [1.1000] * 3 + list(np.linspace(1.1000, 1.1065, 30)) + list(np.linspace(1.1065, 1.1000, 30))
    m = make(c, path)
    st = setup_at(m, int(m.tf["M1"].t_open[1]), sweep_low=1.0981)
    tr = simulate(st, "sweep_wick", "trailing", m, ExecContext(m.tf["M5"], 50), [], c)
    assert tr.exit_reason == "trail_stop"
    assert tr.r_mult == pytest.approx(2.0, abs=0.06)
    trp = simulate(st, "sweep_wick", "partial", m, ExecContext(m.tf["M5"], 50), [], c)
    assert trp.r_mult == pytest.approx(0.5 * 3 + 0.5 * 0.0, abs=0.06)  # half at 3R, rest at break-even
