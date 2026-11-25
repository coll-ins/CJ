import numpy as np
import pandas as pd

from cjfx.data.bars import build_all
from cjfx.synthetic import random_walk_m1


def test_daily_and_h4_alignment(cfg):
    m1 = random_walk_m1("2023-07-02", "2023-07-20", seed=2)
    b = build_all(m1, cfg["calendar"])
    d = b["D"]
    # every daily bar opens at 17:00 New York (21:00 UTC in July)
    opens = pd.DatetimeIndex(d["open_time"]).tz_convert("America/New_York")
    assert ((opens.hour == 17) & (opens.minute == 0)).all()
    h4 = b["H4"]
    hrs = h4.index.tz_convert("America/New_York").hour
    assert set(hrs) <= {17, 21, 1, 5, 9, 13}
    # no bar closes before it opens, and HTF bars close no earlier than their last minute
    assert (h4["close_time"] > h4.index).all()
    m1_last = m1.groupby(np.searchsorted(h4.index.as_unit("ns").asi8, m1.index.as_unit("ns").asi8, side="right") - 1).apply(lambda x: x.index.max())
    assert (pd.DatetimeIndex(h4["close_time"]).as_unit("ns").asi8 >= pd.DatetimeIndex(m1_last.values).as_unit("ns").asi8 + 60 * 10**9).all()


def test_weekly_contains_sunday_session(cfg):
    m1 = random_walk_m1("2023-01-01", "2023-01-21", seed=2)
    w = build_all(m1, cfg["calendar"])["W"]
    first = pd.DatetimeIndex(w["open_time"]).tz_convert("America/New_York")
    assert (first.dayofweek == 6).all() and (first.hour == 17).all()


def test_ohlc_consistency(cfg):
    m1 = random_walk_m1("2023-01-01", "2023-02-01", seed=4)
    b = build_all(m1, cfg["calendar"])
    for tf in ("M5", "H1", "H4", "D"):
        x = b[tf]
        assert (x["bid_h"] >= x[["bid_o", "bid_c"]].max(axis=1)).all()
        assert (x["bid_l"] <= x[["bid_o", "bid_c"]].min(axis=1)).all()
        assert (x["ask_c"] >= x["bid_c"]).all()
