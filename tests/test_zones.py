import numpy as np

from cjfx.market import Series
from cjfx.zones import find_zones


def _series(o, h, l, c):
    n = len(o)
    t = np.arange(n, dtype=np.int64) * 4 * 3600 * 10**9
    o, h, l, c = map(np.asarray, (o, h, l, c))
    s = Series(t, t + 4 * 3600 * 10**9, o, h, l, c, o, o, h, l, c)
    s.atr = np.full(n, 1.0)
    return s


def _fx(cfg, **kw):
    fx = dict(cfg["fixed_for_now"])
    fx["swing_k"] = dict(fx["swing_k"], h4=1)
    fx.update(kw)
    return fx


def build(base_bars):
    # bars 0..3 make a swing high at index 1 (k=1), then a drift, the base, and an impulse
    o = [10, 11, 10.5, 10.4] + [b[0] for b in base_bars] + [9.0, 10.0, 12.5, 13.0, 13.0]
    c = [10.5, 11.2, 10.4, 10.0] + [b[1] for b in base_bars] + [10.0, 12.6, 13.0, 13.1, 12.9]
    h = [max(a, b) + 0.1 for a, b in zip(o, c)]
    l = [min(a, b) - 0.1 for a, b in zip(o, c)]
    return o, h, l, c


def test_consecutive_zone(cfg):
    o, h, l, c = build([(10.0, 9.6), (9.6, 9.3), (9.3, 9.0)])
    z = find_zones(_series(o, h, l, c), _fx(cfg), "consecutive_3")
    assert len(z) == 1
    assert z[0].base == (4, 5, 6)
    assert z[0].top == max(h[4:7]) and z[0].bottom == min(l[4:7])


def test_nearest_allows_gap_consecutive_does_not(cfg):
    o, h, l, c = build([(10.0, 9.6), (9.6, 9.7), (9.7, 9.3), (9.3, 9.0)])  # a bullish candle inside the base
    s = _series(o, h, l, c)
    assert find_zones(s, _fx(cfg), "consecutive_3") == []
    zn = find_zones(s, _fx(cfg), "nearest_3")
    assert len(zn) == 1 and zn[0].base == (4, 6, 7)


def test_impulse_too_small_no_zone(cfg):
    o, h, l, c = build([(10.0, 9.6), (9.6, 9.3), (9.3, 9.0)])
    assert find_zones(_series(o, h, l, c), _fx(cfg, impulse_atr_h4=50.0), "consecutive_3") == []
