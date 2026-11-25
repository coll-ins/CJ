"""H002 v0.6 M-11: BTC signal data = Exness BTCUSDm bid ticks -> M1 bid bars (from 2017-09)."""
import io
import zipfile
from pathlib import Path

import pandas as pd

from cjfx.h002.spread_archive import BASE, _get, list_months

out_dir = Path(__file__).parents[1] / "data/exness_m1/BTCUSDm"
out_dir.mkdir(parents=True, exist_ok=True)
for y, m in list_months("BTCUSDm"):
    f = out_dir / f"{y}_{m:02d}.parquet"
    if f.exists():
        continue
    name = f"Exness_BTCUSDm_{y}_{m:02d}"
    try:
        raw = _get(f"{BASE}/BTCUSDm/{y}/{m:02d}/{name}.zip")
    except Exception as e:
        print("SKIP", y, m, e, flush=True)
        continue
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), usecols=[2, 3, 4], names=["ts", "bid", "ask"], header=0)
    df.index = pd.to_datetime(df.pop("ts"), utc=True, format="ISO8601")
    b = df["bid"].resample("1min").ohlc().dropna()
    a = df["ask"].resample("1min").ohlc().dropna()
    bars = pd.concat([b.add_prefix("bid_").rename(columns=lambda c: c.replace("open", "o").replace("high", "h").replace("low", "l").replace("close", "c")),
                      a.add_prefix("ask_").rename(columns=lambda c: c.replace("open", "o").replace("high", "h").replace("low", "l").replace("close", "c"))], axis=1).dropna()
    bars.index.name = "time"
    bars.to_parquet(f)
    print(y, m, len(bars), flush=True)
