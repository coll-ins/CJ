# H002 specification: weekly premium/discount and liquidity sweep-reclaim

| Version | Date | Status | Change |
|---|---|---|---|
| v0.1 | 2026-11-25 | review | `docs/h002_review.md` (commit bec0175), 10 open questions |
| v0.2 | 2026-11-25 | **PROPOSED, not frozen** | collins's decisions of 25 Nov applied; exact rules below |

H002 is not coded and not run. It is frozen only when collins approves this file and
`config/h002.yaml`; the approving commit hash is then written here and in the config. Any later
rule change creates v0.3+ and restarts any forward record.

Related: H001 frozen at commit `897b2d5` (code, config and reports untouched). The old
M5 breakout-fade file is now `docs/h003_candidate_m5_breakout_fade.md` (renamed in `d62f48b`,
contents unchanged, `git log --follow` shows its history). Registry: `docs/hypotheses.md`.

Items marked **[A-n]** are assumptions not covered by collins's decisions. They are listed in
section 9 and need approval like everything else.

## 1. Data and time

* Instruments, never pooled: EURUSD, XAUUSD, BTCUSD, GBPUSD, USDJPY, NAS100.
* Sources: HistData M1 bid (FX, gold, NAS100 as NSXUSD), timestamps fixed EST = UTC-5 with no
  DST, converted by adding exactly 5 hours. Binance BTCUSDT spot M1 (UTC) from 2017-08-17.
* Every timestamp in H002 is UTC. A bar is labelled by its open time and is usable only after
  its close.
* Confirmation candles M5, M15, H1 are built from M1 on UTC clock boundaries
  (M15 at :00/:15/:30/:45, H1 on the hour). An incomplete bar (missing M1 inside) is still
  built from the minutes that exist **[A-1]**.
* **Week** = Monday 00:00 UTC to the next Monday 00:00 UTC. **Month** = UTC calendar month.
* PWH/PWL = high/low of all M1 bars in the previous completed week. Usable from the current
  week's Monday 00:00 UTC. PMH/PML likewise, usable from the 1st of the month 00:00 UTC.
* **Consequence to accept [A-2]:** FX, gold and NAS100 reopen on Sunday about 21:00 to 22:00
  UTC. Under a Monday boundary those Sunday-evening hours belong to the week that is ending,
  so (a) they can set that week's high/low, and (b) trades signalled on Sunday evening use the
  levels of the week before. This is what a Monday 00:00 UTC boundary means; it is stated so
  nobody is surprised later.
* Exness server time is not assumed. It is checked separately (`docs/exness_server_time_check.md`).

## 2. Liquidity levels

### 2.1 PWH/PWL and PMH/PML
One level each per week (month). A level starts **active**, and ends as **retired** after its
first reclaim, **consumed** by the max-penetration rule (3.3), or **expired** at the end of its
week (month) when a new level replaces it.

### 2.2 EQH/EQL (H1)
* Pivot high at H1 bar i: `high[i] > max(high[i-3..i-1])` and `high[i] > max(high[i+1..i+3])`
  (strict both sides, ties are not pivots; same code as H001). Confirmed at the close of
  bar i+3, never earlier. Mirror for lows.
* When pivot P is confirmed, it joins a cluster with an earlier confirmed pivot Q of the same
  side if all of:
  - `|P - Q| <= 0.1 x ATR14(H1)`, ATR through bar i+3 (the confirmation bar);
  - the oldest and newest pivots in the cluster are at most 5 trading days apart, counting
    Mon to Fri UTC dates for FX/gold/NAS100 and all dates for BTC **[A-3]**;
  - no H1 high between Q and P (exclusive) exceeded the cluster level by the instrument's
    minimum penetration (3.1); otherwise Q was already swept and is dead.
* A cluster needs at least 2 confirmed pivots. Level price = the most extreme pivot
  (highest high / lowest low). The touch count stored at signal time = number of pivots in
  the cluster at that moment.
* Cluster life: active until retired or consumed, or **expired 5 trading days after its newest
  pivot [A-4]**.
* If a pivot is within tolerance of two clusters, it joins the most recent one **[A-5]**.

### 2.3 Weekly premium/discount
* `EQ = (PWH + PWL) / 2`, `band = 0.05 x (PWH - PWL)`.
* Measured at the swept level's price L: `L > EQ + band` premium, `L < EQ - band` discount,
  otherwise neutral. Above PWH counts as premium, below PWL as discount.
* Aligned = long in discount, short in premium. Neutral is never aligned.
* Not applied to PWH/PWL (structurally redundant: a PWL is always discount, a PWH premium).

## 3. Sweep, reclaim and invalidation (exact)

Written for a high level L (bearish setup). Lows are the mirror image. All prices are bid.

### 3.1 Minimum penetration p_min (fixed, not derived from any spread value)

| Instrument | p_min | In price | Reason |
|---|---|---|---|
| EURUSD | 1.0 pip | 0.00010 | about 1.3% of a typical ~75 pip daily range |
| GBPUSD | 1.0 pip | 0.00010 | about 1.1% of ~90 pip |
| USDJPY | 1.0 pip | 0.010 | about 1.3% of ~75 pip |
| XAUUSD | 1.5 bp of L | e.g. $0.30 at $2,000 | price went $1,050 to $4,000+; a fixed $ size would mean 4x different things |
| BTCUSD | 5 bp of L | e.g. $15 at $30,000 | price went $3,200 to $120,000+ |
| NAS100 | 1.5 bp of L | e.g. 2.25 pts at 15,000 | index went 2,000 to 21,000+ |

Rationale: about 1% of a typical day's range, so a 0.1 pip print on the bid feed does not count
as a sweep. The daily-range figures are my approximations, **not measured on the data [A-6]**.
The thresholds are frozen as written whatever a later measurement shows; measuring first and
then setting them would be the retrospective adjustment collins ruled out.

### 3.2 State machine per level and confirmation TF
For each completed confirmation candle c (high_c, close_c) while the level is active:

1. **Not yet swept.** If `high_c >= L + p_min`: the level is swept, `sweep_bar = c`,
   `extreme = high_c`, `deadline = open_time(sweep_bar) + 60 min`. Continue to step 2 with the
   same candle (same-candle sweep and reclaim is allowed).
2. **Swept, waiting.** Update `extreme = max(extreme, high_c)`. Then, in this order:
   - **Reclaim**: `close_c < L` (strictly) and `close_time(c) <= deadline` gives a signal.
     The level is **retired**.
   - **Consumed**: `close_c > L + 1.0 x ATR14(conf TF)`, ATR through candle c-1. The level is
     **consumed**, no signal.
   - **Window expired**: `close_time(c) >= deadline` with no reclaim. The level is
     **retired, no signal [A-7]** (one attempt per level).
   - Otherwise wait for the next candle.

Window in candles: M5 = 12 (sweep candle + 11), M15 = 4, H1 = 1. **On H1 the window is the
sweep candle itself**, so H1 confirmation only ever trades same-candle sweep-reclaims. That is
what "60 minutes" implies; flagging it because it makes H1 a different animal from M5.

A close exactly at L is not a reclaim. A level whose first trade beyond it is a weekly-open
gap still follows the same rules; gap sweeps are tagged for a separate breakdown.

### 3.3 Entry, stop, target, exit
* **Entry**: next M5 open after the reclaim candle closes (for M15/H1 that is the same instant
  as the next M15/H1 open). Short fills at bid open minus slippage; long fills at bid open +
  spread + slippage (same convention as H001 `sim.py`).
* **Stop** (short): `extreme + 0.1 x ATR14(conf TF, through the reclaim candle) + spread`,
  triggered when the bid reaches `extreme + buffer` (ask = bid + spread). Long: `extreme -
  buffer - spread`, triggered on the bid **[A-8]**.
* **R** = |entry fill - stop|. **Target** = entry ± 3R, resting limit, no slippage.
* **Minimum stop**: if `R < 3 x (spread + 2 x slippage)` the signal is logged as
  "eligible, not executed (stop too small)".
* **No maximum stop.**
* **End of week**: any open trade is closed at the open of the last M1 bar of the instrument's
  week (before Monday 00:00 UTC), minus slippage.
* **Same-bar stop and target**: resolved on M1; if both are inside one M1 bar, it is a stop.
  A stop gapped through fills at the bar open minus slippage.
* **One open trade per instrument per cell.** Signals that arrive while a trade is open are
  logged as "eligible, not executed (position open)".
* **Overlapping levels**: if two sources signal on the same reclaim candle, the trade is taken
  once per cell (each cell has one source anyway) and tagged with all sources it touched.

### 3.4 Costs
* Exness MT5 Standard: commission 0.
* Spread: constant floor per instrument until Exness spread logs exist. EURUSD 1.0 pip
  (dailyforex average, read 2026-11-25). GBPUSD 1.3, USDJPY 1.2, XAUUSD $0.25, BTCUSD $20,
  NAS100 2.0 pts are **unverified guesses [A-9]**. BTC's constant $20 is badly wrong in
  relative terms at $4,000 vs $90,000 **[A-10]**.
* Slippage per side: EURUSD/GBPUSD/USDJPY 0.2 pip, XAUUSD $0.05, BTCUSD $5, NAS100 0.5 pt
  (guesses, as H001).
* Swap: 0 until the Exness swap table is entered. The end-of-week exit caps holding at 5 days
  but gold, NAS100 and BTC swaps can be material **[A-11]**.
* Stress: every primary result is rerun at 1.5x spread.

## 4. Experiment design

### 4.1 Periods
| Period | Label | Role |
|---|---|---|
| 2011-01-01 to 2023-12-31 (BTC from 2017-08-17) | historical exploratory validation | primary family is tested here; the data has been looked at through H001, so it is not a clean confirmatory sample |
| 2024-01-01 to latest data (Nov 2026) | exposed | run once, reported; can disqualify (E < 0), cannot qualify |
| Exness demo, start after freeze | prospective forward | the only out-of-sample evidence |

### 4.2 Stages
0. Unit tests (section 6) pass. Data-quality report per instrument. No outcomes looked at.
1. Event study per source and TF: forward move after each reclaim in ATR units at
   1, 4, 12, 24 H1 bars, minus the same-hour-of-week mean (H001 diagnostics method). Descriptive.
2. Trade simulation of the primary family (4.3) on 2011 to 2023, plus placebos (4.5).
3. Exposed period run once for the primary family.
4. Combinations of components that passed, pre-written before they are run, as a new family.
5. Forward demo (section 8) only for cells that meet section 7.

### 4.3 Primary confirmatory family (frozen at 54)
| Source | Filter | TF | Cells / instrument |
|---|---|---|---|
| PWH/PWL | none (redundant) | M5, M15, H1 | 3 |
| EQH/EQL | none, aligned | M5, M15, H1 | 6 |
| **Primary total** | | | **9 x 6 = 54** |

Descriptive only, outside the family, always reported: PMH/PML x {none, aligned} x 3 TF =
6 x 6 = 36 cells, with nominal t-stats labelled "not corrected, not a candidate".

For the record: had PMH/PML been included, the family would be 90 and the Bonferroni bar
|t| >= 3.45. With 54 it is **|t| >= 3.31** (two-sided 0.05/54). Primary = 54, frozen.

The "aligned" cell is a subset of the "none" cell, so tests are correlated. That is handled by
the joint bootstrap below, not ignored.

### 4.4 Statistics
* Unit = net R per executed trade. Headline: expectancy, t, trades.
* **Dependence-aware**: stationary block bootstrap over weeks (mean block 4 weeks, 10,000
  draws, fixed seed), resampling the same weeks for all 54 cells at once so cross-cell and
  serial correlation are kept **[A-12]**. CIs are bootstrap percentile; t = mean / bootstrap SE.
* **Multiple testing**: Romano-Wolf stepdown on those joint draws, familywise 5% (primary).
  Bonferroni |t| >= 3.31 reported alongside. Deflated Sharpe counting 54 trials.
* Also reported per cell: eligible setups, executed, skipped by reason, win rate, profit
  factor, expectancy, max drawdown (R and % at 0.5% risk), per-trade and annualised daily
  Sharpe, average holding time, by year, by direction, by session (Asia 00-07, London 07-12,
  NY 12-21, other, UTC), gap vs non-gap sweeps, and touch count for EQH/EQL.

### 4.5 Placebo levels (falsification)
* **Random-offset week levels**: for each week, `L' = PWH + u x (PWH - PWL)` and
  `PWL - u x (PWH - PWL)`, u ~ Uniform(-0.5, 0.5), 200 draws, seed fixed in config.
  Same rules otherwise. A PWH/PWL cell must beat the 95th percentile of its 200 placebo
  expectancies.
* **Stale levels**: high/low of the week before last. Reported.
* **Unequal pivots** for EQH/EQL: single confirmed H1 pivots that are not in any cluster,
  same age limit. An EQH/EQL cell must beat this placebo with a bootstrap 95% CI on the
  difference above zero.
* Placebos are not candidates and not in the family.

### 4.6 Power assumptions (stated so they can be checked)
* SD per trade ≈ 1.73R, from a +3R/-1R outcome at a 25% win rate. Time exits and costs lower it
  slightly, so trade counts below are slightly conservative.
* Trades needed for an observed expectancy E to reach t = 3.31: E 0.20 → 822, 0.25 → 526,
  0.30 → 365. For 80% power at a true E: 0.20 → 1,292, 0.25 → 827, 0.30 → 574.
* Expected counts are **estimates**: previous-day sweep + close-back fired about 130 times a
  year per FX instrument (H001 diagnostics, H1 close-back). Weekly levels have 1/5 of the
  opportunities → PWH/PWL ~25 to 40 a year, ~330 to 520 per FX instrument 2011 to 2023,
  160 to 260 for BTC. The first-reclaim rule, 60-minute window and minimum-stop skip will cut
  this, possibly by half. If a PWH/PWL cell ends below 400 executed trades it is reported as
  "insufficient evidence" regardless of its t.

## 5. Records
Every eligible setup is written to `results/h002/setups.parquet` with level source, level price,
availability time, sweep bar, extreme, reclaim bar, premium/discount state, touch count, ATRs,
stop, R, skip reason. Trades in `trades.parquet`. PMH/PML rows are kept, never dropped.
Reports go in new `reports/2026-MM-DD_h002_*` folders; nothing older is overwritten.

## 6. Unit tests (written before the engine, must pass before any run)

UTC boundaries
1. HistData EST row `2020-03-09 00:00` (EST) becomes `2020-03-09 05:00 UTC` (no DST jump in March).
2. A week with M1 bars from Sun 21:05 UTC to Fri 21:55 UTC: Sunday-evening bars are assigned to
   the **previous** week; PWH for the following week includes them.
3. PWH is NaN for every bar before Monday 00:00 UTC of the week it belongs to, and equals the
   previous week's max from that bar on (no bar of the current week leaks in).
4. PMH on 2024-03-01 00:00 UTC equals the February 2024 high (leap day included); NaN before.
5. BTC weekend bars belong to the week starting the preceding Monday.

Pivot confirmation
6. A pivot at bar i is invisible at bars i..i+2 and visible from the close of i+3.
7. Equal highs (ties) on the left or right do not create a pivot.
8. Two pivots 0.09 x ATR apart cluster; 0.11 x ATR apart do not (ATR fixed in fixture).
9. Pivots 5 trading days apart cluster; 6 do not; a weekend between FX pivots is not counted.
10. A cluster whose first pivot was exceeded by p_min between the two pivots is not formed.
11. The cluster's touch count at signal time excludes pivots confirmed after the signal.

Sweep and reclaim
12. Same-candle: high = L + p_min, close = L - tiny → signal on that candle.
13. high = L + p_min - one tick → no sweep.
14. close exactly = L → no reclaim.
15. M5: reclaim on the 12th candle → signal; on the 13th → none, level retired.
16. H1: sweep candle closes above L → no signal, level retired.
17. Close > L + 1 ATR before any reclaim → level consumed, later reclaim ignored.
18. After a reclaim, a second sweep of the same level → no signal.
19. M15 confirmation: entry time = close of the M15 reclaim candle = open of the next M5 bar.

Stop and target ambiguity
20. Stop and target both inside one M5 bar but in different M1 bars → whichever M1 bar comes
    first wins.
21. Both inside one M1 bar → stop.
22. Price gaps through the stop at the weekly open → fill at the open minus slippage, loss > 1R.
23. Trade still open at the last bar of the week → closed there, outcome "time_exit".
24. Short stop triggers on bid >= extreme + buffer, not on bid >= stop price.
25. R below 3 x round-trip cost → no trade, setup logged with skip reason.

## 7. Evidence required before a forward demo (per instrument and cell)
1. Net expectancy > 0 with Romano-Wolf adjusted p < 0.05 (Bonferroni reference |t| >= 3.31).
2. At least 400 executed trades in 2011 to 2023.
3. Positive in at least 9 of 13 years (BTC 5 of 7).
4. Longs and shorts each non-negative.
5. Still positive at 1.5x spread and at buffers 0.05 and 0.2 x ATR (reported, never selected).
6. Beats its placebo (4.5).
7. Deflated Sharpe > 0.95 with 54 trials.
8. Exposed period expectancy not negative.

## 8. Forward demo protocol
* Exness MT5 Standard demo, code and config frozen at a recorded commit, no live account.
* Only cells meeting section 7. Log real bid/ask, spread at signal and fill, fill price,
  slippage, swap, and every eligible-but-skipped signal.
* No changes mid-test; any change is a new version and restarts the record.
* Kill early if cumulative R falls below the backtest's 5th-percentile path for the same number
  of trades.
* A few months can only confirm that signals, fills and costs match the backtest. A +0.30R edge
  needs ~133 trades to reach t = 2, which at 25 to 40 trades a year is 3 to 5 years per
  instrument. No real money until the pre-registered prospective requirement is met.

## 9. Unresolved assumptions (need approval)

| # | Assumption | Proposal |
|---|---|---|
| A-1 | Bars with missing M1 minutes | build from what exists; log gaps > 30 min; no fill-forward |
| A-2 | Sunday-evening FX hours belong to the ending week under the Monday boundary | accept as a consequence of the chosen boundary |
| A-3 | "Trading days" for the EQ 5-day limit | Mon to Fri UTC dates for FX/gold/NAS100, all dates for BTC |
| A-4 | EQH/EQL cluster lifetime | expires 5 trading days after its newest pivot |
| A-5 | Pivot near two clusters | joins the most recent cluster |
| A-6 | p_min values in 3.1 rest on approximate typical daily ranges, not measured | freeze as written |
| A-7 | Window expires with no reclaim | level retired, no second attempt |
| A-8 | "Plus spread" in the stop buffer for longs, whose stops trigger on the bid anyway | apply to both sides as approved (extra cushion on longs) |
| A-9 | Spread floors other than EURUSD are guesses | use them, flag results; replace with Exness demo spread logs before the forward demo |
| A-10 | BTC constant $20 spread across a 30x price range | switch BTC to a proportional spread of 2 bp of price, or keep $20; needs a decision |
| A-11 | Swap = 0 | accept for stage 2, enter the Exness swap table before stage 3 if collins can export it from the demo terminal |
| A-12 | Bootstrap block length and draws | mean block 4 weeks, 10,000 draws, seed fixed |
| A-13 | ATR length for buffer, max penetration and EQ tolerance | 14 periods of the stated TF, Wilder smoothing as in H001 |
| A-14 | Slippage values | as H001 (guesses) |
| A-15 | Session buckets for the breakdown | UTC Asia 00-07, London 07-12, NY 12-21, other |
| A-16 | Sharpe | per-trade R Sharpe and annualised daily-equity Sharpe at 0.5% risk, both reported |
| A-17 | Placebo design | 200 random-offset draws, stale week-before-last levels, unequal single pivots |
| A-18 | NAS100 data is HistData NSXUSD (a CFD-like index feed), not the Exness US100 feed | accept; differences checked in the forward demo |
| A-19 | Event-study horizons in stage 1 | 1, 4, 12, 24 H1 bars |
