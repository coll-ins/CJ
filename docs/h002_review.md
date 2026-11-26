# H002 review: weekly premium/discount and liquidity sweep-reclaim

Status: pre-coding review, 25 Nov 2026. Nothing has been coded or run for this hypothesis.
Every rule marked **OPEN** needs collins's approval before code is written. Numbers marked
**estimate** are derived from H001 diagnostics, not from an H002 run.

## 0. Naming clash (fix first)

`docs/h002_preregistration.md` already exists and pre-registers a different idea: fading M5
swing breakouts on EURUSD and GBPUSD. Two different hypotheses cannot both be H002.

Proposal: rename that file to `docs/h003_candidate_m5_breakout_fade.md`, label it
"H003-candidate (not run)", and make the weekly sweep-reclaim study H002 with its own
`docs/h002_spec.md`, `config/h002.yaml`, version history and `reports/h002_*` folders.
H001 code, config and reports stay frozen at commit `897b2d5`.

## 1. Interpretation

H002 asks one question: when price trades beyond a "liquidity" level (previous week high/low,
previous month high/low, or a cluster of equal pivots) and a candle then closes back on the
original side, is the next move in the reclaim direction large enough to pay a 3R target
after costs, more often than chance? A second question is whether that answer improves when
the trade direction agrees with where price sits in the previous week's range
(longs in discount, shorts in premium).

Read strictly, it is a mean-reversion test at pre-defined levels. Nothing in the brief
requires a trend, bias, zone or structure break. That makes it simpler and much better
specified than H001, which is good.

### Priors from data already seen (not out-of-sample)

* **Previous-day sweep + close-back** (H1 close back inside, 2011 to Nov 2026, about 2,000
  events per FX instrument): t-stats at 12 H1 bars were EURUSD 0.5, XAUUSD -1.2, BTCUSD -0.2,
  GBPUSD 0.4, USDJPY -1.8, NAS100 0.8. No instrument reached |t| = 2. Weekly and monthly
  levels are the same mechanism on a slower clock. My prior is that H002 is most likely null.
* **M5 swing breaks do reverse** (t -4.3 EURUSD, -4.6 GBPUSD), but by 0.3 to 0.6 pip against a
  1.0 to 1.3 pip spread. A reclaim on M5 is a conditional version of that effect. If H002 shows
  anything on M5, the first suspicion is that it is the same tiny reversal, which costs kill.
* **H001 MFE**: only 8% of sweep-type setups reached 3R before the stop; expectancy was
  negative at every target from 0.5R to 5R. A 3R target needs a win rate above 25% plus costs.

### A structural problem in the brief

**The premium/discount filter is redundant for PWH/PWL sweeps.** A bullish PWL reclaim
happens at the previous week's low, which is by definition the bottom of the discount half.
A bearish PWH reclaim is by definition in premium. The filter would remove zero PWH/PWL
trades. It only does something for PMH/PML and EQH/EQL. The matrix below drops the
meaningless cells instead of counting them as tests.

## 2. Missing or ambiguous rules (OPEN, need approval)

Time and boundaries

1. **Week and month boundary.** The brief says completed UTC candles. H001 used the 17:00
   New York day boundary with DST. These give different PWH/PWL for FX: with UTC weeks the
   Sunday-evening open (about 21:00 to 24:00 UTC) belongs to a different week than under
   New York 17:00. My understanding is that Exness MT5 server time is UTC+0, so UTC matches
   what collins sees on the demo charts (unverified, check the terminal clock). Decide:
   UTC, or New York 17:00 like H001. Also decide the week start: Sunday 00:00 UTC (MT5 W1
   bars) or Monday 00:00 UTC (ISO). For BTC (trades 7 days) this changes the levels.
2. **Weekend and holiday gaps.** If Monday opens beyond PWH/PWL, does the gap count as
   "traded above/below"? Proposal: yes, but report gap-sweeps as their own subgroup.

Sweep and reclaim

3. **"Price approaches a level"** is undefined. Proposal: drop it. Any trade beyond the
   level counts as the sweep.
4. **Minimum penetration.** On bid data a 0.1 pip poke counts. Proposal: at least 1 pip
   (FX) or the instrument's spread floor, fixed per instrument.
5. **Maximum penetration.** At what depth is it a breakout, not a sweep? Proposal: if price
   closes a confirmation candle more than X beyond the level, the level is consumed and no
   reclaim trade is allowed. X needs a value (for example 1 x ATR(14) of the confirmation TF).
6. **Reclaim window.** How many candles after the first trade beyond the level may the
   close-back happen? Without a limit, any level crossed twice in a week is a "reclaim".
   Proposal: a fixed number of confirmation-TF candles (for example 12 M5 = 1 hour,
   4 M15, 1 to 2 H1). Needs a number.
7. **Repeat sweeps.** After a reclaim, price can trade beyond the same level again. First
   reclaim per level only, or every reclaim? Proposal: first reclaim only, then the level is
   retired for the rest of the week (or month).
8. **Same-candle sweep and reclaim.** A candle that wicks beyond and closes back counts as
   both. Proposal: yes (this is the commonest form).
9. **Overlapping levels.** PWL, PML and an EQL can sit within a few pips. Proposal: one
   trade per instrument at a time; a signal is credited to every source it touches for the
   per-source report, but simulated only once.
10. **Which candle confirms at M15/H1.** Proposal: the sweep and the reclaim are both judged
    on the confirmation TF's completed candles; entry is the next M5 open after that candle
    closes (identical to the next M15/H1 open).

Equal highs and lows

11. **Pivot timeframe and strength.** Proposal: pivots on H1 with k = 3 bars each side,
    confirmed only k bars after the pivot (same swing code as H001).
12. **Tolerance.** Proposal: two pivots are "equal" if within 0.1 x ATR(14, H1) at the
    second pivot. Needs approval; it is the parameter most likely to be tuned after the fact.
13. **Minimum touches** (proposal 2) and **maximum age** of the first pivot (proposal 5
    trading days), and the level price (proposal: the most extreme pivot in the cluster).
14. **Which EQH/EQL are "relevant"?** The brief says "relevant liquidity level" and never
    defines relevance. Proposal: all unswept clusters, no relevance filter.

Premium and discount

15. **Equilibrium band.** "At equilibrium = neutral" needs a width. Proposal: within 5% of
    the PW range of the midpoint is neutral.
16. **Price outside the previous week's range.** Above PWH is premium, below PWL is
    discount? Proposal: yes.
17. **Measured where?** Proposal: the swept level's price, not the entry price.

Risk and execution

18. **Stop buffer.** Must be fixed before running. Proposal: sweep extreme +
    0.1 x ATR(14) of the confirmation TF + spread (shorts stop on the ask). One value,
    sensitivity at 0.05 and 0.2 reported but never selected.
19. **Minimum and maximum stop.** On M5 a sweep can leave a 2 pip stop, where a 1.4 pip
    round-trip cost is 0.7R. Proposal: skip trades whose stop is below 3 x round-trip cost;
    record them as "eligible, not executed". No maximum.
20. **Time exit.** A 3R target from an M5 entry at a weekly level may take days. Proposal:
    close at the end of the trading week if neither stop nor target is hit (avoids weekend
    gaps; swap is not modelled, so long holds are under-costed anyway).
21. **Session filter.** The brief is silent. Proposal: none in the baseline, sessions
    reported as a breakdown only.
22. **News filter.** No economic-calendar data is loaded. Proposal: none, stated as a
    limitation.
23. **Sharpe definition.** Proposal: per-trade R Sharpe plus annualised Sharpe of daily
    equity at 0.5% risk per trade.

## 3. Look-ahead and leakage risks

| Risk | Where it bites | Control |
|---|---|---|
| Using the current (incomplete) week or month for PWH/PWL/PMH/PML | levels | A level becomes usable only from the open of the next week/month; unit test on a week boundary |
| Timezone shift | HistData stamps are fixed EST (UTC-5, no DST); one wrong hour moves weekly levels | convert once, test against known Sunday opens |
| Pivots used before they are confirmed | EQH/EQL | a pivot exists only k bars after it forms |
| Counting touches that happen later | EQH/EQL touch count | count touches only up to the signal bar |
| Higher-TF candle used before its close | M15/H1 confirmation | entry no earlier than the confirmation candle's close |
| ATR including the current bar | buffer, max-penetration, tolerance | ATR through the last completed bar only |
| Stop and target in the same bar | 3R exits | M1 path check; if still ambiguous, count as a stop |
| Bid-only data | sweeps detected on bid; real spreads widen at the 17:00 NY rollover and the bid dips, creating fake PWL sweeps; constant spread hides this | flag signals in the rollover hour as a subgroup; later replace with Exness spread logs |
| Researcher leakage | 2011 to Nov 2026 has been looked at through H001, including sweeps of previous-day levels | no historical period is a clean holdout; only the forward demo is |
| Selecting instruments, tolerances or buffers after seeing results | everywhere | all values frozen in `config/h002.yaml` before the first run, commit hash recorded in the report |

## 4. Isolating each variable

The baseline is fixed: **PWH/PWL source, M5 confirmation, no filter, fixed 3R, fixed buffer**.
Each comparison changes one thing and reports the difference with its own confidence interval.

1. **Does the level matter at all? (event study, no trade mechanics)** For every reclaim,
   measure the forward move in ATR units over fixed horizons, minus the average move at the
   same hour of week, exactly like the H001 diagnostics. This tests direction without the
   3R/stop choices in the way.
2. **Placebo levels.** Run the identical rules on levels that should not matter: the high/low
   of the week before last (stale levels), and random levels placed at the same distance
   from price as PWH/PWL. If the real levels do no better than placebos, "liquidity" adds
   nothing. Placebos are not candidates and do not enter the test family.
3. **Level source.** PWH/PWL vs PMH/PML vs EQH/EQL, each with everything else at baseline.
4. **Premium/discount filter.** Split each source's trades into "aligned" vs "not aligned"
   (paired on the same event set) and test the difference, not a separate strategy. Not
   tested for PWH/PWL (redundant, section 1).
5. **Confirmation TF.** Same levels, M5 vs M15 vs H1.
6. **Combinations** only after a component passes on its own, and only combinations
   written down before stage 2 starts.

Everything is reported per instrument (never pooled), by year, by direction (long/short),
by source and with/without filter, as the brief lists.

## 5. Experiment matrix

Stage 1 (confirmatory family, 2011-01-01 to 2023-12-31; BTC 2017-08-17 to 2023-12-31):

| Source | Filter states | Confirmation TF | Cells per instrument |
|---|---|---|---|
| PWH/PWL | none (filter is redundant) | M5, M15, H1 | 3 |
| PMH/PML | none, aligned | M5, M15, H1 | 6 |
| EQH/EQL | none, aligned | M5, M15, H1 | 6 |
| **Total** | | | **15 x 6 instruments = 90 tests** |

No parameter grid: every number in section 2 is a single frozen value. That keeps the family
at 90 instead of thousands (H001 ran 13,824 configs).

**Corrected significance bar.** Romano-Wolf stepdown on the 90 cells at familywise 5% is
primary. The Bonferroni reference is |t| >= 3.45 (two-sided 0.05/90). If PMH/PML is dropped
(question 5 below) the family is 54 and the bar is |t| >= 3.31.

**Trades needed.** A +3R/-1R trade at a ~25% win rate has a standard deviation of about
1.73R. The trades needed for an observed net expectancy E to reach the bar:

| Net expectancy E (R) | 0.10 | 0.15 | 0.20 | 0.25 | 0.30 |
|---|---|---|---|---|---|
| Trades for t = 2.0 (single test) | 1,200 | 533 | 300 | 192 | 133 |
| Trades for t = 3.45 (90 tests) | 3,571 | 1,587 | 893 | 571 | 397 |

For 80% power (not just a 50/50 chance of clearing the bar) at t = 3.45, a true E of
0.20 / 0.25 / 0.30R needs 1,380 / 883 / 613 trades.

**Expected trade counts (estimate).** Previous-day sweep-and-close-back fired about
130 times a year per FX instrument in the H001 diagnostics. Weekly levels have one fifth of
the opportunities, monthly about one twentieth, so roughly:

| Source | Per year, per instrument | 2011 to 2023, FX/gold/NAS | BTC 2017 to 2023 |
|---|---|---|---|
| PWH/PWL | 25 to 40 | 330 to 520 | 160 to 260 |
| PMH/PML | 6 to 9 | 80 to 120 | 40 to 60 |
| EQH/EQL | depends on tolerance, likely hundreds | 1,000+ | 500+ |

What that means, bluntly:

* **PWH/PWL**: with ~400 trades, only an observed E of about +0.30R or more can clear the
  corrected bar. A smaller real edge is undetectable here.
* **PMH/PML**: ~100 trades. The bar would require E of about +0.60R. This source cannot be
  tested meaningfully on one instrument. Either report it as descriptive only (and drop
  it from the family), or accept it will almost surely come back "insufficient evidence".
* **EQH/EQL** is the only source with enough events, and also the one with the most free
  parameters (pivot TF, k, tolerance, touches, age). That is exactly where overfitting hides,
  so its parameters must be frozen before the first run.

Stage 2 (only if anything passes stage 1): pre-written combinations of passing components,
treated as a new family with its own correction. Stage 3: the exposed period 2024-01-01 to
the latest data is run once, labelled "exposed, not out-of-sample". It can disqualify a
candidate (negative E) but cannot qualify one.

## 6. Minimum evidence before recommending a forward demo

All of the following, per instrument and cell, on 2011 to 2023 with costs:

1. Net expectancy > 0 with Romano-Wolf adjusted p < 0.05 (about |t| >= 3.45).
2. At least 400 executed trades (below that, the result is "insufficient evidence"
   whatever the t-stat says).
3. Positive in at least 9 of 13 calendar years (BTC: 5 of 7). Alone that is weak
   (13% chance under a coin flip), so it is a robustness check, not proof.
4. Long and short both non-negative, so one trending period does not carry it.
5. Still positive at 1.5x the spread floor, and at stop buffers of 0.05 and 0.2 x ATR.
6. Beats the placebo levels by a margin with a 95% interval above zero.
7. Deflated Sharpe ratio above 0.95 counting all 90 trials.
8. Not negative on the exposed 2024 to Nov 2026 period.

Under the null, with 90 tests and this correction, the chance of a false pass is about 5%
in total. Given the previous-day prior (no |t| above 2 on any instrument), I expect most or
all cells to fail.

### Forward demo protocol (the only clean test left)

* Exness MT5 Standard demo, code frozen at a recorded commit, rules and pass bar written
  down before day 1. Log real bid/ask, spread, slippage and swap on every trade.
* Only cells that passed all 8 points above. No changes during the test; a change restarts it.
* **Honest limit:** a weekly-level strategy fires 25 to 40 times a year per instrument. Even a
  real +0.30R edge needs about 133 trades to show t = 2 once, which is about 3 to 5 years on
  one instrument. A 3 to 6 month demo cannot prove an edge. It can only check that live fills,
  spreads and signal counts match the backtest within tolerance, and kill the strategy early
  if cumulative R falls below the backtest's 5th-percentile path.
* No real money until the forward record alone clears t >= 2 on the pre-registered rule.

## Open questions for collins (numbered for approval)

1. Rename the existing M5 breakout-fade file to H003-candidate so this becomes H002?
2. Week/month boundary: UTC (matches Exness charts if server time is UTC+0) or New York
   17:00 like H001? And does the week start Sunday or Monday?
3. Sweep definition: minimum penetration, maximum penetration before it is a breakout, and
   the reclaim window (section 2, items 4 to 6).
4. First reclaim per level only, then the level is retired?
5. PMH/PML has about 100 trades per instrument: keep it in the tested family (it will almost
   surely be "insufficient evidence") or report it as descriptive only (family 54, bar 3.31)?
6. EQH/EQL: pivot TF and k, tolerance, minimum touches, maximum age (items 11 to 14).
7. Premium/discount: neutral band width, and measure at the level or at entry?
8. Stop buffer value, minimum stop size, and the end-of-week time exit (items 18 to 20).
9. Session and news filters: none in the baseline?
10. Accept the 8-point evidence bar and the forward-demo protocol, including that the demo
    is a sanity check, not proof?
