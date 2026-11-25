import numpy as np

from cjfx.indicators import last_confirmed_swing_high, structure_state, swing_highs, swing_lows


def test_swings_strict():
    h = np.array([1, 2, 3, 5, 3, 2, 1, 2, 2, 1.0])
    sh = swing_highs(h, 3)
    assert list(np.where(sh)[0]) == [3]
    assert not swing_highs(np.array([1, 2, 3, 3, 2, 1, 0.0]), 2).any()  # ties are not swings


def test_last_confirmed_swing_high_no_lookahead():
    h = np.array([1, 2, 3, 5, 3, 2, 1, 2, 2, 1.0])
    lvl = last_confirmed_swing_high(h, 3)
    # swing at 3, confirmed at close of 6, usable from bar 7
    assert np.isnan(lvl[:7]).all()
    assert (lvl[7:] == 5).all()


def test_structure_clear_break_and_neutral():
    # swing high 5 at index 3 (k=2), confirmed by bar 5; bar 7 closes at 5.1 (small) then new swing, bar 13 clear break
    h = np.array([1, 2, 3, 5, 3, 2, 2, 5.2, 4, 3, 2, 3, 6, 4, 3, 2, 3, 9.0])
    l = h - 1
    c = h - 0.1
    a = np.full(len(h), 1.0)
    st = structure_state(h, l, c, 2, 0.25, a)
    assert st[6] == 0
    assert st[7] == 0          # 5.1 - 5 = 0.1 < 0.25 ATR -> neutral
    assert st[-1] == 1         # 8.9 well above swing high 6 -> bullish
    lo = swing_lows(l, 2)
    assert lo.any()
