# H002 specification: weekly premium/discount and liquidity sweep-reclaim

| Version | Date | Status | Change |
|---|---|---|---|
| v0.1 | 2026-11-25 | review | `docs/h002_review.md` (commit bec0175), 10 open questions |
| v0.2 | 2026-11-25 | proposed | collins's decisions of 25 Nov applied (commit c438a24) |
| v0.3 | 2026-11-25 | proposed | H001.1 brief merged in (collins chose: same study as H002); items 1 to 5 of collins's conditional sign-off recorded; BTC spread 2 bp withdrawn, cost source = Exness tick export; swap labelled omitted with break-even and scenario sensitivity |
| v0.4 | 2026-11-26 | final draft | collins's confirmation of A-1 to A-23 and research principles (section 10); undefined details I-1 to I-3 (section 11); collins's 8 clarifications on A-1 to A-23 applied: unscorable events on data gaps, labels on estimates, spread units and conversions frozen, slippage sensitivity, NSXUSD proxy, no duplicate filter tests; family count check (section 4.3) |
| v0.5 | 2026-11-26 | **FINAL DRAFT for freeze approval, not frozen** | spread source = Exness public tick archive (Standard `m` series, monthly hour-of-week medians), first-12-month profile before archive start, signals unchanged; I-1 A, I-2 A, I-3 B |

H002 is not coded and not run. It is frozen only when collins approves this file and
`config/h002.yaml`; the approving commit hash is then written here and in the config. Any later
rule change creates a new version (v0.6+) and restarts any forward record.

Related: H001 frozen at commit `897b2d5` (code, config and reports untouched). The old
M5 breakout-fade file is now `docs/h003_candidate_m5_breakout_fade.md` (renamed in `d62f48b`,
contents unchanged, `git log --follow` shows its history). Registry: `docs/hypotheses.md`.

**H001.1 = H002.** collins's H001.1 brief (25 Nov, 21:08 UTC) describes this same study and
collins chose to treat them as one. Its additions are in sections 4.7 to 4.9. H001 is the frozen
benchmark (`docs/h001_frozen.md`, commit cb7c990 on `claude/project-thread-mqtukq`).

Items marked **[A-n]** are assumptions not covered by collins's decisions. They are listed in
section 9; all were approved on 26 Nov (eight with clarifications).

## 1. Data and time

* Instruments, never pooled: EURUSD, XAUUSD, BTCUSD, GBPUSD, USDJPY, NAS100.
* Sources: HistData M1 bid (FX, gold, NAS100 as NSXUSD), timestamps fixed EST = UTC-5 with no
  DST, converted by adding exactly 5 hours. Binance BTCUSDT spot M1 (UTC) from 2017-08-17.
* Every timestamp in H002 is UTC. A bar is labelled by its open time and is usable only after
  its close.
* Confirmation candles M5, M15, H1 are built from M1 on UTC clock boundaries
  (M15 at :00/:15/:30/:45, H1 on the hour).
* **Data gaps [A-1, approved with clarification].** A gap is any run of **5 or more consecutive
  missing M1 bars** inside the instrument's normal trading hours (scheduled weekend closure and
  the daily maintenance break excluded). If a gap overlaps any part of an event's sequence,
  from the sweep candle's open through the trade's exit (or through the end of the reclaim
  window for a non-traded setup), the event is **unscorable**: logged with reason
  `data_gap`, never simulated, never counted as a win or loss. No price path is inferred or
  filled. Shorter runs (1 to 4 missing minutes) are treated as no trades printed; a
  sensitivity rerun with the strict rule (any missing minute = gap) is reported.
* A week or month whose own M1 data has a gap is flagged `levels_degraded`; its PWH/PWL
  (PMH/PML) are still used but results are also reported with those weeks excluded.
* **Week** = Monday 00:00 UTC to the next Monday 00:00 UTC. **Month** = UTC calendar month.
* PWH/PWL = high/low of all M1 bars in the previous completed week. Usable from the current
  week's Monday 00:00 UTC. PMH/PML likewise, usable from the 1st of the month 00:00 UTC.
* **Consequence to accept [A-2]:** FX, gold and NAS100 reopen on Sunday about 21:00 to 22:00
  UTC. Under a Monday boundary those Sunday-evening hours belong to the week that is ending,
  so (a) they can set that week's high/low, and (b) trades signalled on Sunday evening use the
  levels of the week before. This is what a Monday 00:00 UTC boundary means; it is stated so
  nobody is surprised later.
* Exness server time is not assumed. It is checked separately (`docs/exness_terminal_evidence.md`, step A); **status: PENDING collins's evidence**.

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
**Label: estimated design choices, not empirically optimised values.** They are frozen as
written whatever a later measurement shows; no retrospective tuning.

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
**Approved (26 Nov) as a separate experiment: H1 confirmation = same-candle sweep-and-reclaim
only. It cannot capture a reclaim on a later H1 candle under the 60-minute rule**, so an H1
result says nothing about slower reclaims.

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

**Evidence held today (25 Nov 2026).** I tried to pull Exness's published spreads and swap
tables; the cloud environment cannot reach exness.com or the broker-review sites, and the
web-search snippets that came back were third-party and contradictory (BTC Standard spread
quoted anywhere from "from 25 points" to "200 to 400 points", no stated point size). None of
that is usable. What exists:

| Instrument | Observation | Source | Weight |
|---|---|---|---|
| EURUSD | 1.0 pip average, Standard | dailyforex review, read 25 Nov | third-party average |
| XAUUSD | bid 3575.057 / ask 3575.278 = **$0.221 = 0.62 bp** | collins's Exness demo screenshot, 26 Nov 00:08 Nairobi (21:08 UTC, late NY session) | **one off-hours tick** |
| all others | none | — | guesses only |

One gold tick does support the $0.25 floor at today's price, but proves nothing about other
hours or about 2011 to 2023, when gold traded at $1,050 to $2,000.

**Commission**: 0 (Exness MT5 Standard).

**Spread, primary value (decided 26 Nov by collins: archive = yes, pre-archive = option A,
signals stay on HistData/Binance; never chosen from results).**
1. Source = Exness's public tick archive (`ticks.ex2archive.com`, see
   `docs/exness_data_access.md`), Standard-account series with suffix `m`: EURUSDm, GBPUSDm,
   USDJPYm, XAUUSDm, BTCUSDm, USTECm. `m` = Standard is inferred from spreads (EURUSDm 0.8 pip =
   Cent series; plain series 0.6 = Pro) and is **pending collins's confirmation** of the demo
   symbol names. If the demo shows a different suffix, that series is used instead and the
   change is recorded before the run.
2. For every instrument and calendar month the archive covers: median spread (ask - bid) of
   all ticks in each hour-of-week bucket (168 buckets, UTC). A trade uses the bucket of its
   own month and hour (stop buffer: the reclaim candle's hour, I-2). An empty bucket falls back
   to that month's overall median.
3. **Before the archive starts** (FX and gold 2011-01 to 2015-07; NAS100 2011-01 to 2019-07;
   BTC 2017-08-17 to 2017-08-31): the profile of the **first 12 archived months** is applied
   and every such trade is tagged `spread_extrapolated`. Results are also reported split by
   archived vs extrapolated period.
4. Unit for the extrapolated period (A-10 rule, now run on the archive's full history instead
   of a 3-month export): regress monthly median spread on monthly mean price; if the slope has
   |t| > 3 and the price range is at least 10%, the first-12-month profile is applied in bp of
   price, otherwise in fixed USD/points. Archived months use their own spreads in price units,
   so no unit question arises there.
5. Signals (sweeps, reclaims, levels, stops, targets) stay on HistData/Binance bid prices as
   approved; the archive is used for costs only. Ask = HistData bid + archive spread.
6. The archive files used are listed with SHA-256 hashes in `results/h002/cost_inputs.csv`,
   and the unit-regression output is written into `config/h002.yaml`, both committed **before**
   any H002 outcome is computed.
7. **Limitation, stated in every report:** the archive is Exness's real Standard spread from
   2015 (FX, gold), 2017 (BTC) and 2019 (NAS100) onward. Earlier years are extrapolated from
   the first archived year; retail spreads were generally wider in the early 2010s, so those
   years are likely under-costed. The 3x spread sensitivity covers that risk.

**Spread units and conversion (frozen before the first run).** Prices are bid. Ask = bid +
spread in price units. One pip/point = `pip_size`.

| Instrument | pip_size | Unit stored | Conversion to price | Example |
|---|---|---|---|---|
| EURUSD | 0.0001 | pips | spread_pips × 0.0001 | 1.0 pip = 0.00010 |
| GBPUSD | 0.0001 | pips | spread_pips × 0.0001 | 1.3 pip = 0.00013 |
| USDJPY | 0.01 | pips | spread_pips × 0.01 | 1.2 pip = 0.012 |
| XAUUSD | 0.1 | **decided from export**: bp or USD | bp × price / 10,000, or USD as is | 0.62 bp at $3,575 = $0.221 |
| BTCUSD | 1.0 | **decided from export**: bp or USD | bp × price / 10,000, or USD as is | 2 bp at $90,000 = $18 |
| NAS100 | 1.0 | **decided from export**: bp or points | bp × price / 10,000, or points as is | 1.5 bp at 20,000 = 3.0 pts |

Unit rule for the three "decided" rows, fixed now: regress spread on mid price over the
export. If the price slope is significant (|t| > 3) and the export's price range is at least
10% wide, use bp; otherwise use fixed USD/points. If the export's price range is under 10% (the
test cannot tell), use bp, because fixed USD across a 4x to 30x price history is the less
plausible model. The chosen unit, the regression output and the export's SHA-256 are written
into `config/h002.yaml` and committed **before** the first run.

**BTC specifically.** The v0.2 proposal of 2 bp is **withdrawn**: it had no observation
behind it. The reasoning that remains is structural: at a constant $20, BTC's cost was 50 bp
of price at $4,000 (2018) and 2 bp at $100,000 (2025), a 25x swing in relative cost driven by
nothing but the price level. A broker spread that stayed fixed in USD across that range is
implausible, but that is an argument, not evidence. The unit and value come from step 2.

**Spread sensitivity (all reported, none selected).** Every primary cell is rerun at 0.5x,
1x, 1.5x, 2x and 3x the primary spread. For BTC also: flat $20 (H001 value), 2 bp, 5 bp and
10 bp. For each cell the report gives the **break-even spread** (the spread at which net
expectancy hits zero), so anyone can compare it against what they see on the terminal.
The pass bar (section 7, point 5) uses 1.5x, fixed in advance.

**Slippage per side [A-14]**: EURUSD/GBPUSD/USDJPY 0.2 pip, XAUUSD $0.05, BTCUSD $5, NAS100
0.5 pt. **Label: estimates**, kept identical to H001 for the primary comparison. Conservative
sensitivity: 2x and 4x these values on entries and stop/time exits (targets stay limit fills),
plus a combined worst case of 2x spread and 2x slippage. Each cell also reports its
break-even slippage. The forward demo records actual slippage.

**Swap: OMITTED from the primary result, not assumed to be zero.** No Exness swap history
exists in the repo, and swap rates change daily, so a historical series cannot be built. Every
results table carries the line "swap omitted, see swap sensitivity".
How big it can get, by arithmetic only (no data):
* **The rates below are illustrative, not actual historical swap, and are never presented as
  such.** Swap per night ≈ price × annual financing rate / 365. At illustrative rates, chosen
  without looking at Exness's table: EURUSD 1.10 × 3% → 0.9 pip; XAUUSD $3,500 × 5% → $0.48;
  NAS100 20,000 × 7% → 3.8 pts; BTCUSD $90,000 × 20% → $49 per night.
* In R: an M5 EURUSD stop of 8 pips makes one 0.9 pip night **0.11R**. Against a 0.30R edge,
  three nights erase it. Swap matters most for trades held over Wednesday (triple swap) and for
  M5 cells with small stops.
* Every executed trade logs nights held (count of 22:00 UTC rollovers crossed, triple on
  Wednesday; BTC daily including weekends).

Swap sensitivity, reported for every primary cell:
1. **Break-even swap**: the adverse swap per night (pips/points and % per year) that takes
   net expectancy to zero. This needs no swap data and is the headline number.
2. Scenario S1: adverse swap on both directions at the illustrative rates above.
3. Scenario S2: 2x S1.
4. Scenario S3: Exness's actual swap long/short from the Specification window
   (`docs/exness_terminal_evidence.md`, step C), applied as constant over history, once
   collins supplies it. Labelled "current rates applied to history".
5. Share of trades held at least one night, and the R distribution by nights held.
A cell passes section 7 only if it stays positive under S1. Whether collins's account has
swap-free status (Exness Personal Area > Trading conditions) is recorded; if it does, the
forward demo will show swap = 0 but S1 still applies to the backtest.

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

**Family count check [A-21, approved with clarification].** A filtered variant exists only
where the filter can change eligibility:

| Source | Can the filter change eligibility? | Variants | x TF | x instruments | Tests |
|---|---|---|---|---|---|
| PWH/PWL | No: a PWL is always discount, a PWH always premium | unfiltered only | 3 | 6 | 18 |
| EQH/EQL | Yes: an EQL can sit in premium, an EQH in discount | unfiltered, aligned | 3 | 6 | 36 |
| **Primary family** | | | | | **54** |
| PMH/PML (descriptive, outside family) | Yes | unfiltered, aligned | 3 | 6 | 36 |

No PWH/PWL "aligned" cell exists anywhere in the spec, config or reports, so there is no
duplicate test. Safeguard for EQH/EQL, fixed now: if in some instrument x TF the aligned set
turns out identical to the unfiltered set (same trades), the two share one result and are
reported as one; the family count stays 54 (frozen), which makes the correction slightly
conservative, never looser. Bonferroni reference |t| >= 3.31; Romano-Wolf primary.

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

### 4.7 Descriptive investigations (H001.1 brief: depth, speed, candle, source, regime)
These are reported for every primary cell, **outside the test family, with nominal statistics
only**. Bucket edges are fixed here, before any run, so they cannot be drawn around a result.

| Variable | Definition | Buckets |
|---|---|---|
| Sweep depth | (extreme - L) / ATR14(conf TF) | <0.25, 0.25-0.5, 0.5-1.0 |
| Reclaim speed | confirmation candles from sweep candle to reclaim candle | same candle, 1-3, 4-11 (M5); same, 1-3 (M15); H1 is always same candle |
| Reclaim candle body | abs(close - open) / (high - low) | <0.33, 0.33-0.67, >0.67 |
| Reclaim close distance | (L - close) / ATR14 for shorts, mirror for longs | <0.1, 0.1-0.3, >0.3 |
| Liquidity source | PW, EQ (primary), PM (descriptive), overlaps tagged | as recorded |
| Volatility regime | ATR14(D1) percentile within the trailing 252 completed days | <33, 33-67, >67 |
| Trend regime | sign of (previous week close - close 4 weeks earlier) vs trade direction | with, against |

Any bucket that looks good is a **new hypothesis**, never a filter added to H002. It would go
in as H00x with its own spec and could only be confirmed on the forward demo, because all
historical data will by then have been used to find it. With 7 variables x ~3 buckets x 9
cells x 6 instruments (about 1,100 comparisons), several nominal |t| > 2 results are expected
by chance alone.

### 4.8 Comparison against H001 (frozen benchmark)
* Same data files (HistData/Binance, same date range), same risk (0.5% per trade, R units).
* Costs: H002 is reported twice: under its primary cost model, and under the **H001 cost
  floors exactly as frozen**, so the comparison with H001's frozen results is like-for-like.
  H001's code and results are not rerun or changed.
* Known non-identical items, stated rather than hidden: H001 used the 17:00 New York day
  boundary and H002 uses UTC; H001 had walk-forward selection over 13,824 configs, H002 has
  no parameter selection.
* Table per instrument: trades, trade frequency per year, win rate, profit factor,
  expectancy, max drawdown, t, for H001 (best walk-forward and full-period figures from its
  reports) and each H002 cell.
* "Out-of-sample robustness" for both can only come from the forward demo (4.1).

### 4.9 Independent review and evidence labels
* **Before freeze**: an independent reviewer (a separate Claude agent given only this spec,
  the config and the data description, not my reasoning) audits it for look-ahead, ambiguity
  and undeclared degrees of freedom. Findings and my responses go in
  `docs/h002_independent_review.md`; collins rules on each.
* **After stage 2**: a second independent agent re-implements the sweep/reclaim state machine
  from this spec alone and must reproduce the signal list for one instrument-year exactly, plus
  20 randomly drawn trades hand-checked against M1 bars.
* Every statement in H002 reports carries one label:
  **[E] established evidence** (measured on our data, with the file/commit),
  **[H] hypothesis** (untested claim), **[U] unverified assumption** (a number or rule taken
  without data, listed in section 9), **[B] backtest result** (with period, cost model and
  whether the data was exposed), **[F] forward-demo result**.

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

Data gaps
26. 5 missing M1 bars inside an open trade → event `data_gap`, no P&L recorded; 4 missing → trade scored.
27. Gap inside the reclaim window of a setup → setup `data_gap`, not a signal and not a "no reclaim".
28. Missing minutes during the scheduled weekend closure or daily break → not a gap.

Costs
29. Spread conversion for each instrument and unit in the 3.4 table returns the example values.
30. Spread 2x and slippage 4x settings change fills by exactly those amounts.

## 7. Evidence required before a forward demo (per instrument and cell)
1. Net expectancy > 0 with Romano-Wolf adjusted p < 0.05 (Bonferroni reference |t| >= 3.31).
2. At least 400 executed trades in 2011 to 2023.
3. Positive in at least 9 of 13 years (BTC 5 of 7).
4. Longs and shorts each non-negative.
5. Still positive at 1.5x the primary spread, under swap scenario S1, and at buffers 0.05 and
   0.2 x ATR (reported, never selected).
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

## 9. Assumptions (A-1 to A-23 approved by collins 2026-11-26; the eight marked "approved with clarification" carry his wording)

All rows are approved. Nothing in this table is a measured fact; every row is an [U] assumption in reports.


| # | Assumption | Proposal |
|---|---|---|
| A-1 | Missing data | **approved with clarification**: a gap of 5+ missing minutes overlapping the sweep-to-exit sequence makes the event unscorable; no path inferred; strict 1-minute rule as sensitivity |
| A-2 | Sunday-evening FX hours belong to the ending week under the Monday boundary | accept as a consequence of the chosen boundary |
| A-3 | "Trading days" for the EQ 5-day limit | Mon to Fri UTC dates for FX/gold/NAS100, all dates for BTC |
| A-4 | EQH/EQL cluster lifetime | expires 5 trading days after its newest pivot |
| A-5 | Pivot near two clusters | joins the most recent cluster |
| A-6 | p_min values | **approved**: frozen, labelled estimated design choices, no retrospective tuning |
| A-7 | Window expires with no reclaim | level retired, no second attempt |
| A-8 | "Plus spread" in the stop buffer for longs, whose stops trigger on the bid anyway | apply to both sides as approved (extra cushion on longs) |
| A-9 | Spread source | **approved, updated 26 Nov**: Exness public tick archive, Standard `m` series, monthly hour-of-week medians (section 3.4); first 12 archived months applied before archive start, tagged extrapolated; 3x sensitivity |
| A-10 | Spread unit for the extrapolated period | **approved, updated 26 Nov**: unit regression (|t| > 3, price range >= 10%) run on the archive's full history; output committed before the first run |
| A-11 | Swap (**approved with clarification**: omission explicit, illustrative rates never shown as actual) | omitted from the primary result and labelled so; break-even swap + scenarios S1 to S3; S1 rates (FX 3%, gold 5%, NAS100 7%, BTC 20% a year) are illustrative, set before any run |
| A-12 | Bootstrap block length and draws | mean block 4 weeks, 10,000 draws, seed fixed |
| A-13 | ATR length for buffer, max penetration and EQ tolerance | 14 periods of the stated TF, Wilder smoothing as in H001 |
| A-14 | Slippage values | **approved with clarification**: H001 values, labelled estimates; 2x, 4x and break-even sensitivity |
| A-15 | Session buckets for the breakdown | UTC Asia 00-07, London 07-12, NY 12-21, other |
| A-16 | Sharpe | per-trade R Sharpe and annualised daily-equity Sharpe at 0.5% risk, both reported |
| A-17 | Placebo design | 200 random-offset draws, stale week-before-last levels, unequal single pivots |
| A-18 | NAS100 proxy | **approved with clarification**: HistData NSXUSD is a proxy, not claimed identical to Exness US100/USTEC; the forward demo logs both and reports level and spread differences |
| A-19 | Event-study horizons in stage 1 | 1, 4, 12, 24 H1 bars |
| A-20 | Equilibrium: the H001.1 brief says "at 50% = equilibrium" (a single price); collins approved a 5% neutral band on 25 Nov | keep the approved 5% band; a zero-width band is reported as a sensitivity |
| A-21 | (**approved with clarification**: filtered variants only where eligibility can change; no PWH/PWL duplicate; see family table 4.3) The H001.1 brief says bullish signals "qualify in discount" (a requirement); H002 tests with and without the filter | keep both; the filtered cell answers the brief, the unfiltered one shows whether the filter adds anything |
| A-22 | The H001.1 brief keeps "price approaches a mapped level" | not used: no definition exists, any trade beyond the level counts (approved in v0.2) |
| A-23 | Descriptive bucket edges and regime definitions (4.7) | as written, fixed before any run |

## 10. Research principles (collins, 26 Nov 2026, binding on every H002 run and report)

1. Approved assumptions are not changed because another version produces better results.
2. Every statement is labelled [E] measured evidence, [H] hypothesis, [U] unverified
   assumption, [B] backtest result or [F] forward-demo result.
3. The six instruments are never pooled to manufacture a stronger result.
4. Promising descriptive buckets never become entry filters inside H002.
5. H002 is allowed to fail; a negative result is reported as fully as a positive one.
6. H001 stays frozen as the benchmark.
7. No live deployment on historical backtest profitability alone.
8. No historical run and no forward-demo recording before collins's freeze approval.

## 11. Implementation details (decided by collins 26 Nov 2026: I-1 A, I-2 A, I-3 B; fixed before the run)

| # | Detail | Option A | Option B | Consequence |
|---|---|---|---|---|
| I-1 | "Normal trading hours" for the gap rule (A-1) | Derived from the data: a minute-of-week counts as normal if the instrument has a bar there in at least 50% of weeks in that year | Fixed broker schedule typed in by hand per instrument | A adapts to HistData's actual session coverage but uses the data to define itself; B needs a schedule we don't have verified for 2011 to 2026 and would mark many quiet-hour minutes as gaps |
| I-2 | Which spread goes into the stop buffer once spread varies by hour of week | Spread at the reclaim candle's hour | Spread at the entry bar's hour | Almost always the same hour; differs only when the reclaim closes on the hour boundary. Effect on R is tiny |
| I-3 | BTC "positive in 5 of 7 years" when 2017 is a partial year (from 17 Aug) | Count 2017 as a year | Count 2018 to 2023 only (6 years, require 4 of 6) | A lets 4.5 months count as a full year; B is cleaner but a weaker test |

**Decided: I-1 = A (normal hours derived from data, 50% of weeks), I-2 = A (spread at the reclaim candle's hour), I-3 = B (BTC years 2018 to 2023, at least 4 of 6 positive).** Section 7 point 3 for BTC reads accordingly.
