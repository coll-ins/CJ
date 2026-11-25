# CJ FX

Research engine for the CJ FX multi-agent trading project. This repository currently holds
**Phase 2 groundwork for Hypothesis 001 (H001)**: a historical FX data pipeline, a mechanical
and fully configurable rule engine, a bid/ask backtester with Exness MT5 Standard costs, and
the walk-forward and multiple-testing harness from the Phase 1 Blueprint (v0.2).

What is deliberately **not** here: no LLM-generated signals, no broker connection, no live or
demo order execution.

The spec is the *CJ FX Phase 1 Blueprint* (v0.2). Every rule option and threshold lives in
[`config/h001.yaml`](config/h001.yaml); the code reads it and hardcodes none of them.
Interpretation choices the blueprint left open are listed in
[`docs/assumptions.md`](docs/assumptions.md). Read that before trusting any result.

## Status

| Piece | State |
|---|---|
| Dukascopy downloader and decoder (bid and ask M1, tick fallback) | Built, unit-tested on synthetic files. Not yet run against the live feed (the cloud workspace that built it could not reach the host). |
| Bars on the 17:00 New York day boundary, DST by time-zone library | Built, tested for summer, winter and the US/UK DST-gap weeks |
| H001 rule engine, 6 strategies x 128 configurations | Built, tested (component tests, long/short mirror symmetry, rule invariants) |
| Backtester (M1 bid/ask path, stop-first on ambiguous bars, gaps, slippage, intraday close) | Built, tested |
| Exness Standard costs | No commission. Spread = max(Dukascopy spread, floor). **Floors are estimates** until Exness tick files are loaded. Swap not modelled (0). |
| Walk-forward (4y train / 1y test, 2015 to 2023), Romano-Wolf, Bonferroni, deflated Sharpe, PBO (CSCV) | Built, tested on synthetic data |
| One-shot holdout (2024 onward) with a ledger that refuses a second run | Built |
| News blackout | Code ready, **off** until a high-impact calendar CSV is supplied |
| Results on real data | **None yet.** |

## Run it

Python 3.10+. On Windows (PowerShell):

```powershell
git clone https://github.com/coll-ins/CJ.git; cd CJ
git checkout claude/project-thread-le9wii
py -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[test]"
pytest -q                                   # should print all tests passed

python -m cjfx.cli download --start 2011-01-01           # ~35,000 small files, 1 to 3 hours
python -m cjfx.cli bars                                   # data quality report -> results/data_quality.json
python -m cjfx.cli grid                                   # all 768 configurations -> results/trades.parquet
python -m cjfx.cli evaluate                               # walk-forward + corrections -> results/report.json
```

On macOS/Linux use `python3 -m venv .venv && source .venv/bin/activate` instead.

Optional inputs:

* `data/exness/EURUSD.csv` (and the other pairs): Exness tick history for the Standard account.
  When present, the spread floor becomes the median Exness spread for that hour of the week,
  and `results/cost_model.json` stops calling the cost an estimate.
* `--news events.csv` on `grid`: columns `time_utc,currency,impact`; entries within
  `news_blackout_minutes` of a `high` event for either currency of the pair are blocked.

After `evaluate`, and only once per strategy:

```bash
python -m cjfx.cli sensitivity --strategy swing_h1:continuation --grid-point "consecutive_3|h1_swing|sweep_wick|fixed_3r|london_ny"
python -m cjfx.cli holdout --strategy swing_h1:continuation
```

The holdout ledger (`results/holdout_ledger.json`) refuses a second run of the same strategy.
`--force` exists, is recorded, and makes that holdout worthless as evidence.

Every `grid` run is appended to `results/trials.jsonl`. The deflated Sharpe ratio uses that
count, so reruns with changed code or settings make the bar harder, as they should.

## Layout

```
config/h001.yaml        the only place rule options, times and thresholds live
cjfx/calendar.py        NY 17:00 trading day, sessions, Friday cutoff (zoneinfo, DST-safe)
cjfx/data/dukascopy.py  download + decode bid/ask (format self-checks)
cjfx/data/bars.py       M1 -> M5, H1, H4, D, W, MN with open/close times; gap report
cjfx/costs.py           Exness Standard spread model
cjfx/indicators.py      ATR, swings, structure state
cjfx/market.py          per-pair view; shorts run the long rules on mirrored prices
cjfx/zones.py           H4 zones (consecutive_3 / nearest_3)
cjfx/levels.py          liquidity levels (h1_swing, prev_day, asian_session, equal_levels)
cjfx/engine.py          zone touch -> sweep -> close-back -> confirmation -> entry
cjfx/sim.py             trade path on M1 bid/ask, all four exits
cjfx/research.py        grid runner, one-open-trade filter, trial ledger, audit sample
cjfx/stats.py           summaries, Romano-Wolf, Bonferroni, DSR, PBO
cjfx/validation.py      walk-forward, verdicts, holdout
cjfx/cli.py             command line
docs/assumptions.md     every interpretation the code makes beyond the blueprint
```
