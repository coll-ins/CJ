"""Binance spot 1m klines from data.binance.vision (BTCUSDT from 17 Aug 2017).

TRADE prices on Binance spot, not the bid/ask of the Exness BTCUSD CFD. The close is used as
the bid and the cost model adds the configured spread floor (ESTIMATE). Trades 24/7.
Monthly zips: data/spot/monthly/klines/{SYM}/1m/{SYM}-1m-{YYYY}-{MM}.zip; daily zips for the
current month. open_time is ms until 2024, microseconds from 2025 (detected by magnitude).
"""
from __future__ import annotations

import io
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://data.binance.vision/data/spot"
SYMBOLS = {"BTCUSD": "BTCUSDT"}
FIRST = date(2017, 8, 1)


def _get(url: str, cache: Path) -> bytes | None:
    if cache.exists():
        return cache.read_bytes() or None
    for k in range(4):
        try:
            b = urllib.request.urlopen(url, timeout=120).read()
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(b)
            return b
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if k == 3:
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if k == 3:
                raise
        time.sleep(2 ** k)
    return None


def parse_zip(b: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        raw = z.read(z.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), header=None, usecols=[0, 1, 2, 3, 4])
    if not str(df.iloc[0, 0]).isdigit():
        df = df.iloc[1:].astype(float)
    t = df[0].astype(np.int64).to_numpy()
    unit = "us" if t.max() > 10**14 else "ms"
    idx = pd.DatetimeIndex(pd.to_datetime(t, unit=unit, utc=True), name="time")
    out = pd.DataFrame({"bid_o": df[1].astype(float).to_numpy(), "bid_h": df[2].astype(float).to_numpy(),
                        "bid_l": df[3].astype(float).to_numpy(), "bid_c": df[4].astype(float).to_numpy()}, index=idx)
    for k in "ohlc":
        out[f"ask_{k}"] = out[f"bid_{k}"]
    return out


def download_range(pair: str, start: date, end: date, cache_dir: Path, workers: int = 4, log=print) -> pd.DataFrame:
    sym = SYMBOLS[pair]
    start = max(start, FIRST)
    cache = Path(cache_dir) / sym
    parts = []
    m = date(start.year, start.month, 1)
    today = date.today()
    while m <= end:
        if (m.year, m.month) < (today.year, today.month):
            name = f"{sym}-1m-{m.year}-{m.month:02d}.zip"
            b = _get(f"{BASE}/monthly/klines/{sym}/1m/{name}", cache / name)
            if b:
                parts.append(parse_zip(b))
                log(f"  {pair} {m:%Y-%m}: {len(parts[-1]):,} bars")
        else:
            d = m
            while d <= min(end, today - timedelta(days=1)):
                name = f"{sym}-1m-{d:%Y-%m-%d}.zip"
                b = _get(f"{BASE}/daily/klines/{sym}/1m/{name}", cache / name)
                if b:
                    parts.append(parse_zip(b))
                d += timedelta(days=1)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    if not parts:
        raise RuntimeError(f"no Binance data for {pair}")
    m1 = pd.concat(parts).sort_index()
    return m1[~m1.index.duplicated(keep="last")]
