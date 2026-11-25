"""Dukascopy historical data (bid AND ask). Free, but the server resets connections from
cloud/datacenter IPs (seen 25 Nov 2026), so run `download` from a home connection.

URL layout: https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM-1:02}/{DD:02}/...
  {BID|ASK}_candles_min_1.bi5  one day of M1 candles
  {HH:02}h_ticks.bi5           one hour of ticks
Files are LZMA-compressed arrays of big-endian records. Month is zero-based.
"""
from __future__ import annotations

import lzma
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://datafeed.dukascopy.com/datafeed"
# seconds from day start, 4 prices in points, volume
CANDLE_DTYPE = np.dtype([("t", ">u4"), ("p1", ">i4"), ("p2", ">i4"), ("p3", ">i4"), ("p4", ">i4"), ("v", ">f4")])
# ms from hour start, ask, bid (points), ask volume, bid volume
TICK_DTYPE = np.dtype([("t", ">u4"), ("ask", ">i4"), ("bid", ">i4"), ("av", ">f4"), ("bv", ">f4")])

# Dukascopy symbol, points per price unit, plausible price range (sanity check on scale).
# Point scales for XAUUSD, BTCUSD and the Nasdaq index are from community decoders, UNVERIFIED;
# the range check rejects a wrong scale instead of silently producing bad prices.
SYMBOLS = {
    "EURUSD": ("EURUSD", 1e5, (0.5, 2.5)),
    "GBPUSD": ("GBPUSD", 1e5, (0.8, 2.6)),
    "USDJPY": ("USDJPY", 1e3, (50.0, 250.0)),
    "XAUUSD": ("XAUUSD", 1e3, (200.0, 10000.0)),
    "BTCUSD": ("BTCUSD", 10.0, (50.0, 1e6)),
    "NAS100": ("USATECHIDXUSD", 1e3, (500.0, 1e5)),
}


class DecodeError(ValueError):
    pass


def _sym(pair: str):
    if pair not in SYMBOLS:
        raise KeyError(f"no Dukascopy symbol mapping for {pair}")
    return SYMBOLS[pair]


def candle_path(pair: str, day: date, side: str) -> str:
    return f"{_sym(pair)[0]}/{day.year}/{day.month - 1:02d}/{day.day:02d}/{side.upper()}_candles_min_1.bi5"


def tick_path(pair: str, day: date, hour: int) -> str:
    return f"{_sym(pair)[0]}/{day.year}/{day.month - 1:02d}/{day.day:02d}/{hour:02d}h_ticks.bi5"


def _check(prices: np.ndarray, pair: str) -> None:
    lo, hi = _sym(pair)[2]
    if len(prices) and not ((prices > lo) & (prices < hi)).all():
        raise DecodeError(f"{pair}: decoded prices {prices.min():.5g}..{prices.max():.5g} outside {lo}..{hi}; wrong point scale?")


def decode_candles(raw: bytes, pair: str, day: date) -> pd.DataFrame:
    """One day of M1 candles -> DataFrame[o,h,l,c,v] indexed by UTC minute. Zero-volume filler dropped.

    Field order is documented inconsistently (OHLC vs OCLH); it is detected per file: the high
    is the field that is >= every other field on every row.
    """
    cols = ["o", "h", "l", "c", "v"]
    if not raw:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], tz="UTC", name="time"))
    rec = np.frombuffer(lzma.decompress(raw), dtype=CANDLE_DTYPE)
    rec = rec[rec["v"] > 0]
    p = np.stack([rec["p1"], rec["p2"], rec["p3"], rec["p4"]], axis=1).astype(np.float64)
    mx, mn = p.max(axis=1, keepdims=True), p.min(axis=1, keepdims=True)
    if (p[:, [1]] == mx).all() and (p[:, [2]] == mn).all():
        o, h, l, c = p[:, 0], p[:, 1], p[:, 2], p[:, 3]          # OHLC
    else:
        o, c, l, h = p[:, 0], p[:, 1], p[:, 2], p[:, 3]          # OCLH
    scale = _sym(pair)[1]
    df = pd.DataFrame({"o": o / scale, "h": h / scale, "l": l / scale, "c": c / scale, "v": rec["v"].astype(float)})
    _check(df["c"].to_numpy(), pair)
    start = pd.Timestamp(day, tz="UTC")
    df.index = pd.DatetimeIndex(start + pd.to_timedelta(rec["t"].astype(np.int64), unit="s"), name="time")
    return df


def decode_ticks(raw: bytes, pair: str, day: date, hour: int) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["bid", "ask"], index=pd.DatetimeIndex([], tz="UTC", name="time"))
    rec = np.frombuffer(lzma.decompress(raw), dtype=TICK_DTYPE)
    scale = _sym(pair)[1]
    df = pd.DataFrame({"bid": rec["bid"] / scale, "ask": rec["ask"] / scale})
    _check(df["bid"].to_numpy(), pair)
    start = pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=hour)
    df.index = pd.DatetimeIndex(start + pd.to_timedelta(rec["t"].astype(np.int64), unit="ms"), name="time")
    return df


def ticks_to_m1(ticks: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for side in ("bid", "ask"):
        r = ticks[side].resample("1min").ohlc()
        for k in ("open", "high", "low", "close"):
            out[f"{side}_{k[0]}"] = r[k]
    m1 = pd.DataFrame(out).dropna()
    return m1[["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]]


def _fetch(url: str, cache: Path, retries: int = 4) -> bytes:
    if cache.exists():
        return cache.read_bytes()
    for k in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                b = r.read()
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(b)
            return b
        except urllib.error.HTTPError as e:
            if e.code == 404:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(b"")
                return b""
            if k == retries - 1:
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if k == retries - 1:
                raise
        time.sleep(2 ** k)
    return b""


def download_day(pair: str, day: date, cache_dir: Path) -> pd.DataFrame:
    sides = {}
    for side in ("bid", "ask"):
        rel = candle_path(pair, day, side)
        sides[side] = decode_candles(_fetch(f"{BASE}/{rel}", Path(cache_dir) / rel), pair, day)
    b, a = sides["bid"], sides["ask"]
    idx = b.index.intersection(a.index)
    if not len(idx):
        return pd.DataFrame()
    out = pd.DataFrame(index=idx)
    for k in "ohlc":
        out[f"bid_{k}"] = b.loc[idx, k]
    for k in "ohlc":
        out[f"ask_{k}"] = a.loc[idx, k]
    return out


def download_range(pair: str, start: date, end: date, cache_dir: Path, workers: int = 6) -> pd.DataFrame:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        parts = list(ex.map(lambda d: download_day(pair, d, cache_dir), days))
    parts = [p for p in parts if len(p)]
    if not parts:
        raise RuntimeError(f"no Dukascopy data for {pair} {start}..{end}")
    return pd.concat(parts).sort_index()
