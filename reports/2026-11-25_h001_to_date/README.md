# H001 run to date (2011 to 25 Nov 2026)

collins asked to test up to the current date. Walk-forward now ends 2026-11-25; **no untouched
holdout remains** (2024-2026 was the holdout). The next honest out-of-sample test is a forward
test on new data.

Data end: HistData FX/gold/NAS100 13 Nov 2026 (HistData publishes with a lag; 14-25 Nov is not
available from it). Binance BTC 24 Nov 2026.

Result: all 36 strategies insufficient evidence. Max trades in any single configuration over the
whole period: 18 (needs 100 in a 4-year train window). 0 walk-forward OOS trades. Romano-Wolf:
0 of 4,608 significant.

Unique setups, full period (sweep-wick stop, fixed 3R, all strategies of an instrument together):

| Instrument | Setups | Since 2024 | Win % | E[R] | t | PF | Max DD % |
|---|---|---|---|---|---|---|---|
| EURUSD | 27 | 5 | 33 | -0.25 | -1.28 | 0.55 | 3.9 |
| XAUUSD | 26 | 7 | 35 | -0.09 | -0.40 | 0.80 | 3.0 |
| BTCUSD (from Aug 2017) | 35 | 18 | 37 | -0.12 | -0.63 | 0.77 | 6.6 |
| GBPUSD | 31 | 5 | 29 | -0.18 | -0.84 | 0.67 | 3.1 |
| USDJPY | 14 | 3 | 21 | -0.48 | -2.41 | 0.24 | 3.4 |
| NAS100 | 7 | 0 | 14 | -0.55 | -2.44 | 0.09 | 1.9 |
