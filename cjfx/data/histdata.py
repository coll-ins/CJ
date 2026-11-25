"""HistData.com free M1 bars (BID ONLY). Reachable from the cloud workspace (checked 25 Nov 2026).

* Files: DAT_ASCII_{SYM}_M1_{YYYY}.csv (full past years) or ..._{YYYYMM}.csv (current year, by month).
  Rows: "YYYYMMDD HHMMSS;open;high;low;close;volume".
* Timestamps are EST *without* daylight saving (fixed UTC-5), per HistData's documentation.
  They are converted to UTC here; the 17:00 New York day boundary is then applied DST-aware.
* Bid only: the ask is set equal to the bid and costs.effective_m1 adds the configured
  spread floor (an ESTIMATE). Real spread widening (news, rollover) is therefore NOT modelled.
* Download needs a per-page token: GET the year page, POST the hidden form to /get.php.
"""
from __future__ import annotations

import io
import re
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://www.histdata.com"
SYMBOLS = {"EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY", "XAUUSD": "XAUUSD", "NAS100": "NSXUSD"}
EST_FIXED_OFFSET = pd.Timedelta(hours=5)  # EST -> UTC, no DST
UA = {"User-Agent": "Mozilla/5.0 (research data client)"}


def _page_url(sym: str, year: int, month: int | None) -> str:
    tail = f"{sym.lower()}/{year}" + (f"/{month}" if month else "")
    return f"{BASE}/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{tail}"


def _fetch_zip(sym: str, year: int, month: int | None, retries: int = 4) -> bytes:
    for k in range(retries):
        try:
            page = _page_url(sym, year, month)
            html = urllib.request.urlopen(urllib.request.Request(page, headers=UA), timeout=60).read().decode("utf-8", "replace")
            fields = dict(re.findall(r'<input type="hidden" name="(\w+)" id="\w+" value="([^"]*)"', html))
            if "tk" not in fields:
                raise RuntimeError(f"no download token on {page}")
            body = urllib.parse.urlencode({k2: fields[k2] for k2 in ("tk", "date", "datemonth", "platform", "timeframe", "fxpair")}).encode()
            req = urllib.request.Request(f"{BASE}/get.php", data=body, headers={**UA, "Referer": page,
                                         "Content-Type": "application/x-www-form-urlencoded"})
            b = urllib.request.urlopen(req, timeout=300).read()
            if b[:2] != b"PK":
                raise RuntimeError(f"not a zip for {sym} {year} {month}: {b[:80]!r}")
            return b
        except Exception:
            if k == retries - 1:
                raise
            time.sleep(3 * 2 ** k)
    raise RuntimeError("unreachable")


def parse_csv(text: bytes | str) -> pd.DataFrame:
    if isinstance(text, bytes):
        text = text.decode("ascii")
    df = pd.read_csv(io.StringIO(text), sep=";", header=None, names=["t", "o", "h", "l", "c", "v"],
                     dtype={"t": str, "o": float, "h": float, "l": float, "c": float, "v": float})
    t = pd.to_datetime(df["t"], format="%Y%m%d %H%M%S") + EST_FIXED_OFFSET
    out = pd.DataFrame({f"bid_{k}": df[k].to_numpy() for k in "ohlc"},
                       index=pd.DatetimeIndex(t, name="time").tz_localize("UTC"))
    for k in "ohlc":
        out[f"ask_{k}"] = out[f"bid_{k}"]  # bid-only source; spread added by the cost model
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def _unzip_csv(b: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        return z.read(name)


def download_range(pair: str, start: date, end: date, cache_dir: Path, workers: int = 2, log=print) -> pd.DataFrame:
    sym = SYMBOLS[pair]
    cache = Path(cache_dir) / sym
    cache.mkdir(parents=True, exist_ok=True)
    today = date.today()
    parts = []
    for y in range(start.year, end.year + 1):
        chunks = [(y, None)] if y < today.year else [(y, m) for m in range(1, (today.month if y == today.year else 12) + 1)]
        for yy, m in chunks:
            f = cache / (f"{yy}.zip" if m is None else f"{yy}{m:02d}.zip")
            current = (yy == today.year and m == today.month)
            if not f.exists() or current:
                try:
                    f.write_bytes(_fetch_zip(sym, yy, m))
                except Exception as e:  # e.g. a month not published yet
                    log(f"  {pair} {yy}{'' if m is None else f'-{m:02d}'}: {e}")
                    continue
            parts.append(parse_csv(_unzip_csv(f.read_bytes())))
            log(f"  {pair} {yy}{'' if m is None else f'-{m:02d}'}: {len(parts[-1]):,} bars")
    if not parts:
        raise RuntimeError(f"no HistData data for {pair}")
    m1 = pd.concat(parts).sort_index()
    m1 = m1[~m1.index.duplicated(keep="last")]
    lo, hi = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    return m1[(m1.index >= lo) & (m1.index < hi)]
