# H003 results: time-series momentum (blended 1/3/12-month trend, vol-scaled, daily)

**Verdict: FAIL. 0 of 6 instruments pass section 5.** None reaches the |t| ≥ 2.64 bar even
before swap. H003 joins H001 and H002 as a documented null. Nothing goes to the forward demo.

Run: spec v0.1 + v0.2 pre-run amendment, frozen 2026-11-26 (docs/h003_frozen.md), seed 20261126,
code `cjfx/h003/`, data to 2026-11-13. All numbers are **[B] backtest**. **PROVISIONAL on swap:
carry (rate differential) omitted, financing modelled as a flat 2% a year (BTC 10%) on notional
(A-1).** The conclusion does not depend on this: the best *ex-swap* t is 1.92 (USDJPY), below the
2.64 bar. Spreads: Exness archive (Standard `m`, inferred); before 2015-08 (NAS100 2019-08)
extrapolated from the first 12 archived months, ×1.5 before 2008.

## 1. Primary family (evaluation period, net of spread, slippage, 2% swap)

| Instrument | Period | Years | Net ann. ret | Net Sharpe | NW t | Boot t | Gross Sharpe (t) | Ex-swap t | Pos. years | Placebo p | vs hist-mean t | vs buy-hold t | DSR | 2024-26 Sharpe | Pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 2001-06..2023 | 22.0 | +0.3% | 0.04 | 0.21 | 0.21 | 0.29 (1.39) | 1.21 | 9/23 | 0.07 | 1.03 | 0.78 | 0.000 | 0.21 | no |
| GBPUSD | 2001-06..2023 | 22.0 | −0.9% | −0.12 | −0.57 | −0.58 | 0.12 (0.54) | 0.38 | 10/23 | 0.24 | 1.25 | 0.77 | 0.000 | −0.86 | no |
| USDJPY | 2001-06..2023 | 22.0 | +1.8% | 0.23 | 1.03 | 1.01 | 0.46 (2.08) | 1.91 | 11/23 | 0.02 | 2.98 | 0.85 | 0.002 | −0.88 | no |
| XAUUSD | 2010-03..2023 | 13.6 | +0.8% | 0.11 | 0.42 | 0.43 | 0.26 (1.05) | 0.88 | 7/14 | 0.22 | −0.67 | −0.67 | 0.000 | 1.14 | no |
| NAS100 | 2011-11..2023 | 12.0 | +2.1% | 0.30 | 1.05 | 1.10 | 0.48 (1.69) | 1.47 | 7/13 | 0.76 | −2.85 | −2.85 | 0.002 | 0.32 | no |
| BTCUSD | 2018-09..2023 | 5.3 | +6.3% | 0.84 | 1.67 | 1.57 | 1.06 (2.10) | 1.92 | 6/6 | 0.03 | 0.22 | −0.36 | 0.022 | 0.90 | no |

Volatility target 10% a year per instrument; realised net vol 7-8% (the blended signal is often ±1/3).

Criteria met (of 7): EURUSD 1 (exposed), GBPUSD 0, USDJPY 2 (beats benchmarks, stress), XAUUSD 1,
NAS100 2, BTCUSD 4 (years, stress, not-drift by long/short rule, exposed). **Criterion 1 (t ≥ 2.64)
fails everywhere; DSR is ≤ 0.02 everywhere.**

Full table: `results/h003/final/family_6.csv`; diagnostics `diagnostics.csv`; portfolio
`portfolio_descriptive.json`.

## 2. What the numbers say

* **There is a small gross trend effect, it is not significant, and costs plus financing take most
  of it.** Gross Sharpe 0.12-0.48 on FX/gold/NAS100, the range the literature predicts for single
  instruments (spec section 6). Spread + slippage cost 0.3-0.4% a year; 2% financing costs 0.9-1.6%
  a year. Break-even flat financing rate: EURUSD 2.4%, GBPUSD 0.8%, USDJPY 4.3%, XAUUSD 3.8%,
  NAS100 6.9% — **this is the number to compare against your real Exness swaps.**
* **NAS100 and BTC "trend" is mostly long drift.** NAS100: a vol-scaled buy-and-hold had Sharpe
  0.81 vs trend 0.30 (t of the difference −2.85: trend is significantly *worse* than holding).
  BTC: 97% of the trend profit came from long positions; buy-and-hold Sharpe 0.83 vs trend 0.84.
* **USDJPY** is the only one that beat both benchmarks (placebo p 0.02, vs historical-mean t 2.98),
  but its own t is 1.03 and it lost 6.6% a year in the exposed 2024-26 period.
* **The clean 2000-2010 FX years did not rescue anything:** EURUSD Sharpe 0.33 (t 0.95), GBPUSD
  0.02, USDJPY −0.14.
* **Power, as warned:** even BTC's net Sharpe of 0.84 gives t 1.67 over 5.3 years. To clear 2.64
  at that Sharpe needs about 10 years of data.

## 3. Diagnostics (outside the family, cannot qualify anything)

* Single lookbacks: no |t| above 1.9 in 17 cells (BTC 30-day 1.86 best).
* No vol scaling: worse than with vol scaling on all 6 (consistent with Kim-Tse-Wald 2016).
* **Volatility-expansion split (your idea):** trend net return on days after σ5d/σ60d > 1.25:
  USDJPY +12.2% a year (t 2.43, 1,068 days), BTC +25.0% (t 2.71, 357 days); EURUSD 0.24,
  GBPUSD 0.48, XAUUSD −0.22, NAS100 0.54. Contracting/neutral days: nothing above |t| 1.6.
  Two of 18 regime cells above t 2 where about 1 is expected by chance, no multiple-testing
  correction, and the two are different asset classes. Not evidence; if you want it pursued it is a
  new pre-registered hypothesis (H005-candidate) and must be tested on data it has not seen
  (only the forward demo now qualifies).
* **Squeeze breakout** (20-day range in lowest quintile, then close breaks it; 5-day forward move in
  σ units): t between −0.77 and 0.55 on FX/gold/NAS100, BTC 1.80 (130 events). Nothing.
* **Descriptive 6-instrument equal-weight portfolio** (you ruled out pooling; reported only):
  2001-2023 Sharpe 0.21, t 0.96; 2024-26 Sharpe 0.57, t 1.19. Even diversified, no significant edge
  at Exness costs with this rule.

## 4. Data-quality notes

* HistData FX starts 2000-05-31; 2001-2002 have missing days (220 and 195 trading days kept),
  returns span those gaps close-to-close. Evaluation therefore starts 2001-06 after warm-up.
* Execution bar missing (fell back to close) on ≤ 0.13% of days.
* Pre-archive (extrapolated) spread share of evaluation days: FX 62%, XAU 39%, NAS100 64%, BTC 0%.
  Spread is not what decides the result: gross t is below the bar too.
* BTC uses Exness BTCUSDm bid only (Binance unreachable, A-2).

## 5. What this does and does not say

* It says: a standard, published trend rule, run per instrument on 2001-2023 data with Exness-level
  costs, shows no significant edge on any of the six instruments, and where it makes money (NAS100,
  BTC) it does no better than simply holding.
* It does not say trend following is fake: the literature edge is at *portfolio* level across 50+
  markets, which this project's six-instrument, no-pooling design cannot test.
* Three hypotheses in, the pattern is consistent: on these six instruments with retail CFD costs,
  neither price-level nor trend signals clear a multiple-testing bar.
