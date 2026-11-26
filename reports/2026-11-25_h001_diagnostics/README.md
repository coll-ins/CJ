# H001 component diagnostics (25 Nov 2026) — descriptive, not a strategy test

Data 2011 to 13 Nov 2026 (BTC Aug 2017 to 24 Nov). The 2024+ data was already used, so nothing
here is out-of-sample. Script: `scripts/h001_diagnostics.py`, code: `cjfx/diagnostics.py`.

## 1. Does each step predict direction on its own?

Event study: forward move after each event, in ATR(14) of the event's timeframe, minus the
average move at the same hour of week (matched on time and volatility). Events thinned to be
non-overlapping. Bid prices, no costs. 162 tests (9 components x 3 horizons x 6 instruments),
so Bonferroni needs |t| > 3.61.

t-stats at the middle horizon (12 H1 bars, or 48 M5 bars for the M5 break):

| Component | EURUSD | XAUUSD | BTCUSD | GBPUSD | USDJPY | NAS100 |
|---|---|---|---|---|---|---|
| H4 zone first touch (impulse 2.0) | 0.3 | -1.4 | -1.5 | 0.1 | 0.9 | 0.6 |
| H4 zone first touch (impulse 1.0) | -0.2 | -3.0 | -0.6 | -0.6 | 0.4 | -0.2 |
| Sweep + close back, prev day | 0.5 | -1.2 | -0.2 | 0.4 | -1.8 | 0.8 |
| Sweep + close back, H1 swing | 0.7 | -1.4 | -2.5 | -0.3 | -0.9 | -0.1 |
| Sweep + close back, Asian session | 0.6 | -1.3 | -1.5 | -0.6 | 0.2 | 0.2 |
| MN and W bias both with trade | -0.8 | 0.4 | 0.2 | 0.1 | 1.0 | -0.3 |
| W bias only | 1.7 | 0.2 | -0.0 | 0.1 | 0.6 | -1.6 |
| H1 swing-break confirmation | -1.6 | 1.9 | 0.5 | -1.0 | 2.7 | 0.5 |
| M5 swing-break confirmation | **-4.3** | -1.3 | -2.6 | **-4.6** | -1.0 | -0.6 |

**None of H001's steps predicts the trade direction.** Zones, sweeps, MN/W bias and the H1
break are all within noise, and the few |t| > 2 are mostly negative.

The only significant results (|t| > 3.61) are **M5 swing breaks reversing**: EURUSD, GBPUSD
(1h and 4h) and BTCUSD (1h). That is short-term mean reversion, the OPPOSITE of what the
confirmation step assumes. Its size is too small to trade: EURUSD -0.31 pip at 1h and -0.47 pip at
4h against a 1.0 pip spread; GBPUSD -0.47 / -0.61 pip against 1.3; BTCUSD -$7.6 against $20.

## 2. Trade paths (unique H001 setups, impulse 1.0, sweep-wick stop; n = 490)

Max favourable excursion before the stop: median 0.52R, 75th percentile 1.24R, 90th 2.58R.
30% reach 1R, 15% reach 2R, 8% reach 3R.

| Fixed target | 0.5R | 1R | 1.5R | 2R | 2.5R | 3R | 4R | 5R |
|---|---|---|---|---|---|---|---|---|
| Hit rate | 52% | 30% | 21% | 15% | 11% | 8% | 5% | 3% |
| Expectancy R | -0.06 | -0.10 | -0.08 | -0.07 | -0.08 | -0.07 | -0.08 | -0.06 |

**The 3R target is not what kills H001.** Expectancy is negative at every target. The entries
have no edge, so no exit can rescue them. (Same-bar stop/target counts as a stop.)
