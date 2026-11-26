> Renamed 2026-11-26: was `docs/h003_candidate_m5_breakout_fade.md` ("H003-candidate"), now **H004-candidate**,
> because H003 is the time-series momentum study (docs/h003_spec.md). Contents below unchanged.

# H002 pre-registration (draft, NOT run) — 25 Nov 2026

Status: written before any H002 backtest. Do not change rules or the pass bar after a run.
Requires collins's go-ahead before it is run.

## What the H001 diagnostics allow

No H001 component (H4 zones, liquidity sweeps, MN/W bias, H1 break) showed directional signal
(reports/2026-11-25_h001_diagnostics). The only significant effect is M5 swing breaks
REVERSING within 1 to 4 hours on EURUSD, GBPUSD and BTCUSD. H002 is the only hypothesis the
data supports: fade M5 breakouts.

## Rules (fixed, no grid)

* Instruments: EURUSD, GBPUSD (BTCUSD excluded: effect < 40% of spread). Never pooled.
* Event: M5 close above the last confirmed M5 swing high (k = 3). Mirror for lows.
* Entry: sell at the next M5 open (buy for the mirrored case). Sessions London+NY only.
* Stop: event bar extreme + 0.1 x ATR(M5) + spread. Exit: after 12 M5 bars (1 hour) or stop.
* One open trade per instrument. Spread = config floor (EURUSD 1.0, GBPUSD 1.3), slippage 0.2 pip/side.

## Pass bar (all required, per instrument)

* Net expectancy after costs > 0 with t >= 3.0 over 2011 to 2026 (one test, two instruments,
  Bonferroni-adjusted from 2.4), at least 1,000 trades.
* Positive in at least 11 of 16 calendar years.
* Forward test on the Exness demo account (the only true out-of-sample left): 3 months, net
  expectancy > 0 on at least 200 trades, before any real money.

## Predicted result

The gross effect (0.3 to 0.6 pip) is smaller than the spread (1.0 to 1.3 pip), so H002 is
expected to FAIL on costs. It is registered so that it is tested at most once, not as a
recommendation.
