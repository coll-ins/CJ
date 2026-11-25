import lzma
from datetime import date

import numpy as np
import pytest

from cjfx.data.dukascopy import CANDLE_DTYPE, TICK_DTYPE, DecodeError, candle_path, decode_candles, decode_ticks, ticks_to_m1


def _candles(rows, order):
    rec = np.zeros(len(rows), dtype=CANDLE_DTYPE)
    for i, (t, o, h, l, c, v) in enumerate(rows):
        vals = (o, h, l, c) if order == "ohlc" else (o, c, l, h)
        rec[i] = (t, *vals, v)
    return lzma.compress(rec.tobytes())


ROWS = [(0, 110000, 110050, 109990, 110020, 5.0), (60, 110020, 110030, 110000, 110001, 3.0), (120, 110001, 110001, 110001, 110001, 0.0)]


@pytest.mark.parametrize("order", ["ohlc", "oclh"])
def test_candle_order_autodetect(order):
    df = decode_candles(_candles(ROWS, order), "EURUSD", date(2020, 1, 2))
    assert len(df) == 2  # zero-volume filler dropped
    assert df.iloc[0]["h"] == pytest.approx(1.10050)
    assert df.iloc[0]["l"] == pytest.approx(1.09990)
    assert df.iloc[0]["c"] == pytest.approx(1.10020)
    assert str(df.index[1]) == "2020-01-02 00:01:00+00:00"


def test_wrong_scale_rejected():
    rows = [(0, 11000, 11005, 10999, 11002, 1.0)]  # would decode to 0.11
    with pytest.raises(DecodeError):
        decode_candles(_candles(rows, "ohlc"), "EURUSD", date(2020, 1, 2))


def test_path_month_zero_based():
    assert candle_path("EURUSD", date(2011, 1, 3), "bid") == "EURUSD/2011/00/03/BID_candles_min_1.bi5"


def test_ticks_decode_and_resample():
    rec = np.zeros(3, dtype=TICK_DTYPE)
    rec[0] = (1000, 150010, 150000, 1.0, 1.0)
    rec[1] = (30000, 150020, 150012, 1.0, 1.0)
    rec[2] = (61000, 150030, 150020, 1.0, 1.0)
    df = decode_ticks(lzma.compress(rec.tobytes()), "USDJPY", date(2023, 5, 1), 10)
    assert df["bid"].iloc[0] == pytest.approx(150.000)
    m1 = ticks_to_m1(df)
    assert len(m1) == 2
    assert m1["bid_h"].iloc[0] == pytest.approx(150.012)
    assert m1["ask_o"].iloc[0] == pytest.approx(150.010)
