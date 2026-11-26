"""Exness public tick archive -> monthly hour-of-week spread profiles (H002 spec v0.5, 3.4).

Costs only. Never touches signal data or outcomes. For each archived month of a series:
median (ask - bid) of all ticks per UTC hour-of-week bucket (0 = Monday 00:00 UTC .. 167),
the month's overall median spread and mean mid price, tick count, and the zip's SHA-256.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://ticks.ex2archive.com/ticks"


def _get(url: str, retries: int = 4) -> bytes:
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return r.read()
        except Exception:  # network hiccup: back off and retry
            if i == retries - 1:
                raise
            time.sleep(2 ** (i + 1))
    raise RuntimeError("unreachable")


def list_months(series: str) -> list[tuple[int, int]]:
    out = []
    for y in json.loads(_get(f"{BASE}/{series}/")):
        if y["type"] != "directory":
            continue
        for m in json.loads(_get(f"{BASE}/{series}/{y['name']}/")):
            if m["type"] == "directory":
                out.append((int(y["name"]), int(m["name"])))
    return sorted(out)


def month_profile(series: str, year: int, month: int) -> tuple[dict, pd.DataFrame]:
    name = f"Exness_{series}_{year}_{month:02d}"
    raw = _get(f"{BASE}/{series}/{year}/{month:02d}/{name}.zip")
    sha = hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        csv = z.read(z.namelist()[0])
    df = pd.read_csv(io.BytesIO(csv), usecols=[2, 3, 4], names=["ts", "bid", "ask"], header=0)
    ts = pd.to_datetime(df["ts"], utc=True, format="ISO8601")
    spread = (df["ask"] - df["bid"]).to_numpy()
    how = (ts.dt.dayofweek * 24 + ts.dt.hour).to_numpy()
    prof = (pd.DataFrame({"how": how, "spread": spread}).groupby("how")["spread"]
            .agg(median="median", p90=lambda x: x.quantile(0.9), size="size").reset_index())
    prof.insert(0, "month", f"{year}-{month:02d}")
    prof.insert(0, "series", series)
    meta = {"series": series, "month": f"{year}-{month:02d}", "file": f"{name}.zip", "sha256": sha,
            "bytes": len(raw), "ticks": int(len(df)), "median_spread": float(np.median(spread)),
            "mean_mid": float(((df["ask"] + df["bid"]) / 2).mean()),
            "first_ts": str(ts.iloc[0]), "last_ts": str(ts.iloc[-1])}
    return meta, prof


def build(series_list: list[str], out_dir: Path, log=print) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    man_p, prof_p = out_dir / "cost_inputs.csv", out_dir / "spread_profiles.csv"
    done = set()
    if man_p.exists():
        done = set(zip(*pd.read_csv(man_p)[["series", "month"]].T.values))
    for s in series_list:
        for y, m in list_months(s):
            key = (s, f"{y}-{m:02d}")
            if key in done:
                continue
            try:
                meta, prof = month_profile(s, y, m)
            except Exception as e:  # e.g. current month stored as day files; logged, not guessed
                log(f"SKIP {s} {y}-{m:02d}: {type(e).__name__}: {e}")
                continue
            pd.DataFrame([meta]).to_csv(man_p, mode="a", header=not man_p.exists(), index=False)
            prof.to_csv(prof_p, mode="a", header=not prof_p.exists(), index=False)
            log(f"{s} {y}-{m:02d} ticks={meta['ticks']} median={meta['median_spread']:.6g}")
