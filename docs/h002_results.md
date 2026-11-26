# H002 results: weekly premium/discount + PWH/PWL/EQH/EQL sweep-reclaim

**Verdict: FAIL.** 0 of 54 primary cells meet section 7. 0 cells have a positive expectancy with
Romano-Wolf p < 0.05. 9 cells are significantly **negative** (RW p < 0.05). H002 joins H001 as a
documented null; no cell goes to the forward demo.

Run: spec v0.6 frozen (docs/h002_frozen.md), code at the commit that adds this file, data 2011-01 to
2026-11-13 (BTC Exness BTCUSDm bid from 2017-09-01, Binance 2017-08-17..31). All statements are
**[B] backtest results**, historical exploratory period 2011-2023 unless marked exposed. Costs:
Exness archive spreads (Standard `m` series, inferred) + estimated slippage **[U]**; swap omitted
from the primary result, see swap columns.

## 1. Section 7 evidence bar, 54 cells

| Criterion | Cells meeting it (of 54) |
|---|---|
| 1. E > 0 and Romano-Wolf p < 0.05 | **0** |
| (reference) Bonferroni \|t\| >= 3.31 | 8, all with **negative** E |
| 2. >= 400 trades 2011-2023 | 8 (all PWH/PWL cells are below 400: 112-364) |
| 3. >= 9 of 13 positive years (BTC 4 of 6) | 1 (EURUSD EQ H1 aligned) |
| 4. longs and shorts both >= 0 | 1 |
| 5. positive at 1.5x spread, S1 swap, buffers 0.05/0.2 | 1 |
| 6. beats placebo | 4 (all with negative E; PW cells beat a placebo that is itself negative) |
| 7. deflated Sharpe > 0.95 (54 trials) | 0 (max 0.06) |
| 8. exposed-period E >= 0 | 4 |
| **All** | **0** |

Expectancy: 3 of 54 cells positive (EURUSD PW H1 +0.015R, EURUSD EQ H1 aligned +0.100R t 0.9,
BTCUSD EQ M15 aligned +0.046R). The other 51 range -0.005 to -0.380R. Full table:
`results/h002/final/stats/family_54.csv` (and `.md`).

Significantly negative after Romano-Wolf: GBPUSD EQ M5 (-0.24R), GBPUSD EQ H1 (-0.27R) and
H1 aligned (-0.30R), USDJPY EQ M15 (-0.28R), USDJPY EQ H1 (-0.30R), XAUUSD EQ M15 (-0.26R),
XAUUSD EQ H1 (-0.33R), NAS100 PW M5 (-0.38R), NAS100 EQ M5 aligned (-0.33R).

## 2. Why it fails

* **No gross edge to pay costs.** Entry spread alone averages 0.10R (EURUSD) to 0.17R (NAS100)
  per trade; stop buffer spread and slippage add more. Net expectancy sits around -0.1 to -0.3R,
  i.e. gross close to zero or below. Break-even spread is below 0.5x the measured spread in 47 of
  54 cells. Under H001's own cost floors the picture is the same (4 of 54 cells marginally positive, none significant).
* **Levels are not special.** EQH/EQL vs unequal single pivots (placebo): 35 of 36 bootstrap 95%
  CIs of the difference include zero; the one that excludes it (GBPUSD H1 aligned) is negative.
  PWH/PWL vs random-offset week levels: real levels lose less than placebo levels in most cells, but
  both are negative; "beating" a losing placebo is not an edge.
* **Stage 1 event study** (forward move after reclaim in H1-ATR units, minus prior-years
  hour-of-week baseline): no |t| above 2.6 at 1/4/12/24 h for any instrument/source, signs mixed.
* **Premium/discount filter adds nothing.** Aligned EQ cells are not better than unfiltered in any
  consistent way; for PMH/PML the aligned set was identical to the unfiltered set in every cell.
* **Descriptive buckets (4.7):** of 1,233 buckets with n >= 30, 5 have nominal t > 2 versus about
  28 expected by chance. All 5 are "held 1+ nights", which is conditional on the trade not having
  stopped out early (an outcome, not a pre-trade feature). Nothing to carry forward.

## 3. Data-quality flags (reported, not used to select anything)

* Unscorable (data_gap) share is above the 2% flag in 47 of 54 cells: FX 1-11%, XAUUSD 7-19%,
  NAS100 8-26%. These are HistData closures overlapping trades. The executed trades are unaffected;
  the risk is that excluded events differ systematically. With E this negative a 26% gap share
  cannot turn any cell positive at the significance bar.
* PWH/PWL produces 25-30 trades a year per instrument, so no PW cell reached 400 trades; even with a
  true edge these cells could only have reported "insufficient evidence".

## 4. Independent check (spec 4.9)

A separate agent given only the spec, config and data rebuilt the sweep/reclaim and EQ cluster
logic. EURUSD 2019: **196 of 196 signals identical** (same level, sweep time, reclaim time and
extreme) across PW/EQ x M5/M15/H1. 20 randomly drawn executed trades recomputed by hand from M1
bars: entry, stop, target, R, outcome, exit price and r all match. One labelling difference: stop and
target exit times are stamped at the close of the hit M1 bar (bar open + 1 min); price and r are
unaffected. Files: `results/h002/independent/`.

Spec points the reviewer called underdetermined (the implementation and the reviewer chose the same
reading, hence the exact match): whether a weekend-window sweep uses up the level's attempt (yes);
B-3 "retired" vs "consumed"; whether the EQ 5-day span counts from the pivot bar or its
confirmation (pivot bar); how A-5 ranks a cluster against a single pivot; whether a raised level can
revive a swept cluster (no).

## 5. Exposed period (2024-01-01 to 2026-11-13), run once

Can disqualify, cannot qualify. 50 of 54 cells negative. The 4 non-negative ones (GBPUSD EQ M5
+0.05R and M5 aligned +0.30R, USDJPY PW H1 +0.04R, BTCUSD EQ H1 aligned +0.11R) are all negative
or insignificant historically. Nothing to act on.

## 6. Comparison with H001 (frozen benchmark)

Same conclusion on the same data: H001 had 0 of 13,824 configurations significant; H002 has 0 of
54 pre-registered cells positive and significant, and 9 significantly negative. Deflated Sharpe with
13,878 trials is 0.000-0.002 everywhere.

## 7. What this does and does not say

* It says: on 2011-2023 bid data with Exness-archive costs, buying a reclaimed weekly or equal
  low and selling a reclaimed weekly or equal high, stop beyond the sweep, fixed 3R target, loses
  money on all six instruments, and the levels behave no differently from random levels.
* It does not test discretionary versions, other targets, or the reverse (breakout) trade. Any of
  those is a new hypothesis with its own spec. The significantly negative cells must **not** be
  flipped and traded on this evidence: the loss is mostly costs, which a reversed trade pays too.
