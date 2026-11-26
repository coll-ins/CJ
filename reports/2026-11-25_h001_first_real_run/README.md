# H001 first real-data run (25 Nov 2026)

Data: HistData M1 bid-only (EURUSD, XAUUSD, GBPUSD, USDJPY, NAS100 from Jan 2011 to 13 Nov 2026),
Binance BTCUSDT 1m (17 Aug 2017 to 24 Nov 2026). Constant spread floors (estimates), swap 0,
no news filter. Walk-forward 2011-2023. The 2024+ holdout was NOT run.

## Result: no strategy can be tested; every one of the 36 is "insufficient evidence"

* 36 strategies (6 instruments x 2 executions x 3 setup types), 128 configs each = 4,608.
* Walk-forward selected nothing: no configuration in any 4-year training window had the
  required 100 trades. The most trades any single configuration produced in 13 years was 15
  (GBPUSD intraday reversal_one). So there are 0 out-of-sample trades and no verdicts.
* Romano-Wolf: 0 of 4,608 configurations significant (minimum adjusted p = 0.996).
* Unique setups 2011-2023 (sweep-wick stop, fixed 3R, all strategies of an instrument together):

| Instrument | Setups | Win rate | Expectancy R | t | PF | Max DD % |
|---|---|---|---|---|---|---|
| EURUSD | 22 | 36.4% | -0.22 | -0.95 | 0.61 | 3.44 |
| XAUUSD | 19 | 36.8% | -0.12 | -0.49 | 0.73 | 2.98 |
| BTCUSD (from 2017) | 17 | 52.9% | +0.13 | 0.45 | 1.35 | 1.70 |
| GBPUSD | 26 | 26.9% | -0.15 | -0.60 | 0.73 | 3.07 |
| USDJPY | 11 | 18.2% | -0.53 | -2.77 | 0.15 | 2.91 |
| NAS100 | 7 | 14.3% | -0.55 | -2.44 | 0.09 | 1.91 |

These are descriptive only (in-sample, tiny n). None is evidence of an edge or of its absence.

## Why so few trades: the zone filter

EURUSD H4, 2011-2026: 1,459 candidate bases (3 bearish H4 candles then a bullish one).
Only 28 pass "close >= zone top + 2.0 x ATR(H4) within 3 H4 bars", 26 after the swing-break
check. impulse_atr_h4 is a draft guess from blueprint v0.1. At 1.0 x ATR: 65 zones; 0.5 x: 94.
Even then, sweep + confirmation + session + MN/W bias cut it further.

Files: report.json (full stats), summary_by_strategy.csv, trades.parquet (all config-trades,
including 2024+ rows that were not evaluated), data_quality.json, cost_model.json.
