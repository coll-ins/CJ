"""H003 data fetch (spec docs/h003_spec.md section 2 and 4.1). Costs and signals only; no P&L here.

python -m cjfx.h003.fetch histdata   -> data/m1/{NAME}_M1_h003.parquet (HistData M1 bid, from first year)
python -m cjfx.h003.fetch spreads    -> results/h003/spread_profiles.csv + cost_inputs.csv (Exness archive)
python -m cjfx.h003.fetch btc        -> data/exness_m1/BTCUSDm/*.parquet (Exness BTCUSDm bid M1)
"""
from __future__ import annotations

import io
import sys
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from cjfx.data import histdata
from cjfx.h002 import spread_archive as SA

ROOT = Path(__file__).resolve().parents[2]
FIRST_YEAR = {"EURUSD": 2000, "GBPUSD": 2000, "USDJPY": 2000, "XAUUSD": 2009, "NAS100": 2010}
SERIES = ["EURUSDm", "GBPUSDm", "USDJPYm", "XAUUSDm", "USTECm", "BTCUSDm"]


def fetch_histdata():
    out = ROOT / "data/m1"
    out.mkdir(parents=True, exist_ok=True)
    for name, y0 in FIRST_YEAR.items():
        m1 = histdata.download_range(name, date(y0, 1, 1), date(2026, 11, 26), ROOT / "data/histdata_cache")
        m1[["bid_o", "bid_h", "bid_l", "bid_c"]].to_parquet(out / f"{name}_M1_h003.parquet")
        print(name, len(m1), m1.index[0], m1.index[-1], flush=True)


def fetch_spreads(series: str):
    SA.build([series], ROOT / f"results/h003/spreads/{series}", log=lambda s: print(s, flush=True))


def fetch_btc():
    out = ROOT / "data/exness_m1/BTCUSDm"
    out.mkdir(parents=True, exist_ok=True)
    for y, m in SA.list_months("BTCUSDm"):
        f = out / f"{y}-{m:02d}.parquet"
        if f.exists():
            continue
        name = f"Exness_BTCUSDm_{y}_{m:02d}"
        try:
            raw = SA._get(f"{SA.BASE}/BTCUSDm/{y}/{m:02d}/{name}.zip")
        except Exception as e:
            print("SKIP", y, m, e, flush=True)
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), usecols=[2, 3], names=["ts", "bid"], header=0)
        df.index = pd.to_datetime(df["ts"], utc=True, format="ISO8601")
        bars = df["bid"].resample("1min").ohlc().dropna()
        bars.columns = ["bid_o", "bid_h", "bid_l", "bid_c"]
        bars.to_parquet(f)
        print("BTC", y, m, len(bars), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "spreads":
        fetch_spreads(sys.argv[2])
    else:
        {"histdata": fetch_histdata, "btc": fetch_btc}[sys.argv[1]]()
