"""End-to-end checks on synthetic data: rule invariants and long/short symmetry."""
import numpy as np
import pandas as pd
import pytest

from cjfx.data.bars import build_all
from cjfx.research import one_open_trade_per_pair, run_pair
from cjfx.synthetic import mirror_m1, random_walk_m1


@pytest.fixture(scope="module")
def runs(cfg):
    m1 = random_walk_m1("2017-01-01", "2020-01-01", seed=3, spread_pips=0.0)
    a, ra = run_pair("EURUSD", build_all(m1, cfg["calendar"]), cfg, log=lambda *x: None)
    b, rb = run_pair("EURUSD", build_all(mirror_m1(m1, 1.2), cfg["calendar"]), cfg, log=lambda *x: None)
    return a, b


def test_produces_trades(runs):
    a, _ = runs
    assert len(a) > 0


def test_mirror_symmetry(runs):
    """With zero spread, every long on the data is the same short on the mirrored data."""
    a, b = runs
    k = ["execution", "setup_type", "config_id", "entry_time"]
    la = a[a.direction == 1].set_index(k)["R"].sort_index()
    sb = b[b.direction == -1].set_index(k)["R"].sort_index()
    assert la.index.equals(sb.index)
    assert np.allclose(la.values, sb.values)


def test_invariants(runs, cfg):
    a, _ = runs
    fx = cfg["fixed_for_now"]
    assert (a["entry_time"] > a["first_touch"]).all()
    assert (a["exit_time"] >= a["entry_time"]).all()
    assert (a["R"] >= -1.6).all()  # slippage/gap can exceed -1R slightly, never wildly
    intr = a[a["execution"] == "intraday_m5"]
    if len(intr):
        ny = intr["exit_time"].dt.tz_convert("America/New_York")
        assert ((ny.dt.hour < 17) | (intr["exit_reason"] != "time_exit")).all()
    fixed = a[a["exit"] == "fixed_3r"]
    assert (fixed["R"] <= fx["target_r"] + 1e-6 + 0.5).all()
    for ses in ("london_ny",):
        x = a[a["entry_sessions"] == ses]
        from cjfx.calendar import in_sessions
        assert in_sessions(pd.DatetimeIndex(x["entry_time"]), cfg["calendar"]["entry_session_sets"][ses], cfg["calendar"]).all()


def test_one_open_trade_per_pair(runs):
    a, _ = runs
    f = one_open_trade_per_pair(a)
    for _, g in f.groupby(["execution", "setup_type", "config_id", "pair"]):
        g = g.sort_values("entry_time")
        assert (g["entry_time"].iloc[1:].values >= g["exit_time"].iloc[:-1].values).all()
