# H001 with impulse size as a grid option (2.0 / 1.5 / 1.0 x ATR(H4))

collins chose to test impulse size (25 Nov 2026). 384 configs per strategy, 36 strategies,
13,824 configurations; deflated-Sharpe trial count 18,432 (all runs so far). Data 2011 to
13 Nov 2026 (BTC from Aug 2017 to 24 Nov). Walk-forward to 2026-11-25, no holdout left.

Result: all 36 strategies still insufficient evidence. Max trades in one configuration: 37
over the whole period (selection needs 100 in a 4-year window). Romano-Wolf: 0 significant.

Unique setups by impulse size (sweep-wick stop, fixed 3R, all strategies of an instrument):

| Instrument | Impulse | Setups | Win % | E[R] | t | PF | Max DD % |
|---|---|---|---|---|---|---|---|
| EURUSD | 2.0 | 27 | 33 | -0.25 | -1.28 | 0.55 | 3.9 |
| EURUSD | 1.5 | 54 | 37 | -0.23 | -1.98 | 0.52 | 6.5 |
| EURUSD | 1.0 | 99 | 33 | -0.16 | -1.41 | 0.70 | 10.3 |
| XAUUSD | 2.0 | 26 | 35 | -0.09 | -0.40 | 0.80 | 3.0 |
| XAUUSD | 1.5 | 48 | 38 | -0.01 | -0.04 | 0.98 | 4.6 |
| XAUUSD | 1.0 | 88 | 39 | -0.02 | -0.18 | 0.95 | 9.2 |
| BTCUSD | 2.0 | 35 | 37 | -0.12 | -0.63 | 0.77 | 6.6 |
| BTCUSD | 1.5 | 66 | 33 | -0.11 | -0.67 | 0.81 | 7.9 |
| BTCUSD | 1.0 | 119 | 39 | +0.06 | 0.46 | 1.12 | 7.5 |
| GBPUSD | 2.0 | 31 | 29 | -0.18 | -0.84 | 0.67 | 3.1 |
| GBPUSD | 1.5 | 47 | 30 | -0.23 | -1.53 | 0.55 | 5.6 |
| GBPUSD | 1.0 | 78 | 33 | -0.17 | -1.30 | 0.68 | 6.6 |
| USDJPY | 2.0 | 14 | 21 | -0.48 | -2.41 | 0.24 | 3.4 |
| USDJPY | 1.5 | 33 | 33 | -0.16 | -0.73 | 0.72 | 6.2 |
| USDJPY | 1.0 | 66 | 35 | -0.21 | -1.39 | 0.64 | 9.5 |
| NAS100 | 2.0 | 7 | 14 | -0.55 | -2.44 | 0.09 | 1.9 |
| NAS100 | 1.5 | 17 | 29 | -0.08 | -0.25 | 0.86 | 2.2 |
| NAS100 | 1.0 | 40 | 28 | -0.19 | -0.86 | 0.71 | 5.8 |

Costs are constant spread estimates on bid-only data and swap is 0, so these are optimistic.
