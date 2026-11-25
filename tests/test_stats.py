import numpy as np
import pandas as pd

from cjfx.stats import bonferroni_t, deflated_sharpe, pbo_cscv, romano_wolf, summarize
from cjfx.validation import walk_forward_strategy


def test_summary_basic():
    s = summarize(np.array([3, -1, -1, -1, 3.0]))
    assert s["trades"] == 5 and abs(s["expectancy_R"] - 0.6) < 1e-12
    assert s["longest_losing_streak"] == 3


def test_romano_wolf_controls_noise():
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, (300, 60))
    _, p = romano_wolf(X, reps=300)
    assert (p <= 0.05).sum() <= 3


def test_romano_wolf_finds_real_edge():
    rng = np.random.default_rng(1)
    X = rng.normal(0, 1, (400, 30))
    X[:, 0] += 0.4
    _, p = romano_wolf(X, reps=300)
    assert p[0] <= 0.05


def test_pbo_noise_near_half_and_dsr():
    rng = np.random.default_rng(2)
    X = rng.normal(0, 1, (320, 40))
    r = pbo_cscv(X, 16)
    assert 0.25 < r["pbo"] < 0.8
    d = deflated_sharpe(X[:, 0], 768, np.var(X.mean(0) / X.std(0)))
    assert d["dsr"] < 0.95
    assert bonferroni_t(768, 1000) > 3.5


def test_walk_forward_uses_only_past(cfg):
    """A config that is great only in test years must never be picked."""
    rows = []
    for y in range(2011, 2024):
        for i in range(150):
            t = pd.Timestamp(f"{y}-03-01", tz="UTC") + pd.Timedelta(hours=i)
            rows.append({"config_id": "a|b|c|d|steady", "entry_time": t, "exit_time": t + pd.Timedelta(hours=1), "R": 0.1, "pair": "EURUSD"})
            rows.append({"config_id": "a|b|c|d|future", "entry_time": t, "exit_time": t + pd.Timedelta(hours=1),
                         "R": -0.5 if y < 2015 else 5.0, "pair": "EURUSD"})
    tr = pd.DataFrame(rows)
    res = walk_forward_strategy(tr, cfg)
    assert res["folds"][0]["picked"] == "a|b|c|d|steady"
