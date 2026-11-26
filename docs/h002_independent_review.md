# H002 independent review (draft)

Reviewer: separate Claude agent. Inputs read: `docs/h002_spec.md` (v0.5, marked FROZEN),
`config/h002.yaml`, `docs/exness_data_access.md`. Nothing else was read: no git history, other
docs, chat logs or reports. Where the spec points to an outside file (H001 `sim.py`,
`docs/h002_frozen.md`, `docs/exness_terminal_evidence.md`), I treat it as **not specified** for this
review.

This review only lists problems. Severity scale:
- **blocker**: two competent implementations produce materially different trade lists or P&L
  for many trades, or the rule as written biases the primary result. It must be resolved before
  any run.
- **major**: can change pass/fail for a cell, inflates false positives, or leaves a choice open
  that could be made after seeing results.
- **minor**: wording, audit trail, descriptive-only, or small effect.

Summary: **4 blockers, 17 majors, 17 minors.**

---

## Blockers

### B-1. End-of-week exit timing is undefined per instrument and contradicts the Monday boundary (3.3, 1, A-2, tests 22 and 23)
3.3 says "closed at the open of the last M1 bar of the instrument's week (before Monday 00:00
UTC)". Section 1 defines the week as Monday 00:00 to Monday 00:00 UTC, and A-2 assigns
Sunday-evening FX/gold/NAS100 bars to the ending week. Read literally, the last M1 bar of an FX
week is **Sunday ~23:59 UTC**. So every trade still open on Friday is held through the weekend
gap and closed about two hours after the Sunday reopen, in the widest-spread hours of the week.
Test 22 ("gaps through the stop at the weekly open") assumes this weekend holding. The other
natural reading is "the last bar before the weekend closure", which is Friday ~20:59 or 21:59
UTC depending on DST.
- *Failure scenario:* Programmer A closes a EURUSD M15 short at Friday 21:59. Programmer B holds
  it to Sunday 23:59, where a 60-pip Sunday gap hits the stop at the open for a loss above 1R.
  Every trade open on Friday evening gets a different outcome, holding time, swap-night count
  and spread bucket. Any Sunday 21:00 to 23:59 signal under A-2 is also force-closed within
  minutes under reading 1, which creates tiny time-exit trades at rollover spreads.
- Also undefined: (a) the exit fill for **shorts**. "Minus slippage" is only correct for longs;
  a short buys at ask = bid + spread (which hour bucket?) + slippage. (b) "Last M1 bar" is only
  known in hindsight when the data has a missing minute, a holiday, or a week with no Sunday
  reopen (Christmas or New Year). That is a small look-ahead, and the holding period then
  depends on data quality. (c) For BTC the last bar is Sunday 23:59, so the rule gives
  structurally different holding periods across instruments, and nothing says this is intended.

### B-2. I-1 "normal hours from data, 50% of weeks per year" cannot represent DST-shifting sessions. It creates systematic false gaps, contradicts A-1, and uses future data (1, A-1, 11 I-1, config `gap_normal_hours`)
A-1 says the scheduled weekend closure and the daily maintenance break are excluded from gap
detection. I-1 replaces that schedule with a per-year 50%-of-weeks rule on UTC minute-of-week.
Sessions and breaks follow New York time, so they move by one hour in UTC for about 34 of 52
weeks a year.
- *Failure scenario (gold, NAS100):* the daily break sits at 21:00 to 22:00 UTC in US summer and
  22:00 to 23:00 UTC in winter. The 22:00 to 23:00 UTC minutes have bars in about 34/52 = 65% of
  weeks, so they count as "normal". In each of the ~18 winter weeks those 60 minutes are missing,
  which is a gap of at least 5 minutes, so **every gold or NAS100 trade open across the winter
  daily break becomes `data_gap`**. The same happens to FX Sunday 21:00 to 22:00 UTC in winter
  (the reopen moves). Combined with B-1 reading 1, every winter weekend-held FX trade is
  unscorable.
- The dropped trades are not random: they are the longer-held ones in one season. This is
  outcome-related selection (see M-6).
- The rule uses the whole calendar year's data, including weeks after the event, to decide
  whether an event is scorable. That is look-ahead in sample selection, and it cannot be
  reproduced live. It is undefined for the partial year 2026 and for BTC on 24/7 Binance (where
  every Binance maintenance outage then counts as a gap).
- A-1 ("scheduled ... excluded") and I-1 (data-derived) give different gap sets. Two
  programmers following different sections get different scorable event lists.

### B-3. EQH/EQL cluster formation is underspecified in ways that change the signal list (2.2, A-5, tests 8 to 11)
This matters doubly because 4.9 requires an independent re-implementation to reproduce the
signal list **exactly**. EQH/EQL make up 36 of the 54 family tests.
1. **Tolerance against what?** "`|P - Q| <= 0.1 x ATR`" with *an* earlier pivot Q. For a cluster
   that already has members, is P tested against any member, every member, the newest member, or
   the cluster level? Chaining (P within tolerance of Q, Q within tolerance of R, P and R 0.18 ATR
   apart) gives different clusters under each reading.
2. **"Cluster level" in the dead-pivot check.** "No H1 high between Q and P exceeded the cluster
   level by p_min". Is the level computed before or after P joins? If P > Q + p_min, an
   intervening H1 high in [Q + p_min, P) kills Q under "level = Q" but not under "level = P"
   (most extreme, including P).
3. **A pivot that itself sweeps an existing cluster.** On EURUSD H1, ATR is often 10 to 15 pips,
   so 0.1 ATR is 1 to 1.5 pips, while p_min is 1.0 pip. A new pivot P can sit within tolerance
   yet at least p_min above the cluster level. Bar i (P's bar) sweeps the cluster on M5/M15/H1
   three hours before P is confirmed. When P confirms, nothing says whether it can join the swept
   or retired cluster, or form a **new** cluster {Q, P} at a higher level. Q is not "dead" because
   the exceeding high is P itself, not a bar *between* Q and P. A new cluster re-arms the same
   liquidity, which is effectively a second attempt and contradicts A-7.
- *Failure scenario:* implementation A re-forms a new EQH at P's price after the old cluster
   retired, and takes a second short the next day. Implementation B treats Q as consumed and takes
   none.
4. Can a pivot already in an active cluster also seed a new cluster? Does A-5 ("joins the most
   recent") use cluster creation time or newest-pivot time? Can a retired or expired cluster's
   pivots be reused?
5. When a 3rd pivot joins and is more extreme (but below L + p_min, so it did not sweep), the
   level price moves. Nothing says whether a level already in "swept, waiting" state has its L
   updated, or whether the touch count/level change resets anything.
6. Trading-day counting for Sunday-evening FX pivots: Sunday is not a Mon to Fri date, and the
   spec does not say which date a Sunday 22:00 pivot gets. Expiry "5 trading days after the
   newest pivot" has no time of day (end of day 5? start of day 6?).

### B-4. Fill and trigger conventions for stops, targets and gapped stops are ambiguous on the short side, and slippage on stops is unstated (3.3, 3.4, test 24)
- **Short stop fill:** the stop is `extreme + buffer + spread(reclaim hour)`, triggered when
  bid >= extreme + buffer. Is the fill the stop price, the stop price + slippage, or the trigger
  bid + spread(the **exit** hour) + slippage? 3.4 says "a trade uses the bucket of its own month
  and hour". I-2 fixes the reclaim hour only for the buffer, not for the exit fill.
- **Slippage on stops in the primary run:** 3.3 gives no slippage for a normal stop fill. 3.4
  sensitivity says "2x and 4x on entries and stop/time exits", which implies stops carry
  slippage in the primary run. R = |entry - stop| then understates the realised loss.
- **Short target:** "entry - 3R, resting limit". A short limit buy fills when the **ask** reaches
  it, i.e. bid <= target - spread. With which hour's spread? Or does the bid touching the target
  count? Ties (touch versus trade-through) are also unstated.
- **Gapped stop:** "fills at the bar open minus slippage". For a short, the correct fill is ask
  open (bid open + spread) **plus** slippage.
- **Long stop:** "extreme - buffer - spread, triggered on the bid". Does it trigger at bid <=
  extreme - buffer - spread (A-8's "extra cushion"), or at extreme - buffer with fill at stop?
  Test 24 covers shorts only.
- *Failure scenario:* on M5 cells with 6 to 10 pip stops, a 0.8 to 1.5 pip difference in the
  target trigger changes the win/loss of every short that tops out near the target. Win rates and
  expectancy differ between implementations by several hundredths of R. That is comparable to
  the edges being tested (0.20 to 0.30R).

---

## Majors

### M-1. A level that is swept and waiting when it expires: undefined (2.1, 2.2, 3.2)
PWH/PWL "expire at the end of the week". A Sunday 23:30 UTC M5 sweep of the current PWH (still
the old week under A-2) with a reclaim at Monday 00:10 crosses expiry. Is the window honoured,
cut at expiry, or is the reclaim valid? The same question applies to PMH/PML at month-end and
to EQ clusters at their 5-day expiry. Sunday reopens are exactly when sweeps-by-gap happen, so
this is not rare.
Related contradiction: 3.2 tags "a level whose first trade beyond it is a weekly-open gap".
Under the Monday boundary, the weekly reopen (Sunday 21 to 22 UTC) happens **before** the new
PWH/PWL become active at Monday 00:00. A new PWH/PWL therefore can never be swept by the weekly
open gap; only the *expiring* level can. Programmers will disagree on what is tagged `gap`.

### M-2. Several levels of the same source signalling together, or while a position is open (3.3)
"Overlapping levels" covers different **sources** only. Inside the EQ cell, two EQH clusters at
different prices can be swept and reclaimed by the same candle, or a second one can signal while
the first trade is open.
- Which level defines L, extreme, stop and premium/discount for the single trade? The extremes
  differ when the sweep candles differ.
- Is the non-traded level retired (its one attempt used up), or does it stay active?
- For "position open" skips: is the skipped level retired?
- *Failure scenario:* A takes the higher EQH's setup with a wider stop; B takes the lower one.
  R, target and outcome differ.

### M-3. The executed trade set depends on cost inputs, so sensitivities silently change the sample (3.3 minimum stop, one trade per cell, 3.4 sensitivities, 7.5)
The minimum-stop skip uses `spread + 2 x slippage`. The position-open skip depends on the
previous trade's exit, which depends on costs. At 1.5x, 2x and 3x spread, or at 2x and 4x
slippage, small-stop trades drop out and later signals become executable. The spec does not say
whether sensitivities hold the primary trade set fixed and only reprice it, or rerun selection.
- *Failure scenario:* small-stop trades are the most cost-sensitive and often the worst. Removing
  them at 1.5x spread can **raise** expectancy, so a cell "passes" criterion 7.5 because of
  selection, not robustness. The same applies to the buffer sensitivity (0.05 and 0.2 ATR change
  R and so the skip set). The spec also does not say which hour's spread the minimum-stop rule
  uses.

### M-4. An entry already beyond the stop or target is not handled (3.3)
Entry is at the next M5 open. When the reclaim candle closes at the end of a session (Friday, or
the daily break for gold and NAS100), the next M5 open is after a gap. That open can already be
above the short stop or below the target, so R is invalid, or the trade is born stopped out.
- *Failure scenario:* reclaim at Friday 20:55; the Sunday 21:05 open gaps above extreme + buffer.
  A fills and immediately takes a loss above 1R; B skips. Nothing says what happens.

### M-5. ATR details referenced to H001 rather than specified (A-13, 2.2, 3.2, 3.3, 4.7)
"Wilder smoothing as in H001" points outside this spec. It does not specify the seed (SMA of the
first 14 TRs, or the first TR), how candles with partial or no M1 data are built or skipped,
whether a weekend gap enters TR (Sunday-stub candles inflate M5 ATR at the reopen), or the
warm-up per instrument start (BTC 2017-08-17). ATR enters tolerance, consumption, buffer and
buckets, so differences propagate into signals. The 4.9 reproduction test would fail on this
alone.

### M-6. The unscorable-event rule selects on outcomes (1 A-1, test 26)
For a traded setup, the gap window runs "through the trade's exit", and the exit depends on the
outcome. Trades that last longer (more time-exits and later targets) are more likely to touch a
gap and be dropped. Quick stops are kept. With B-2 the dropped set is also seasonal. Not
specified: whether a `data_gap` trade blocks later signals under the one-position rule, and
whether its level is retired.
- *Failure scenario:* gold M5 shorts that would have hit +3R overnight are disproportionately
  removed in winter, which biases expectancy downward. If gaps cluster in quiet hours, a different
  sign is possible. Either way, the bias is unmeasured. Required but missing: a report of the
  outcome of unscorable trades scored on the available bars, as a bias check.

### M-7. The extrapolated-spread rules contradict each other and carry stale v0.4 text (3.4 steps 3 and 4; unit table; "BTC specifically"; config `unit_rule`)
- Step 4: regress **monthly median spread on monthly mean price over the full archive**. If
  |t| > 3 and range >= 10%, use bp, "otherwise" fixed USD/points. The unit table paragraph instead
  regresses **spread on mid price over the export** (a v0.4 artefact; the export no longer
  exists), and if the range is < 10%, uses **bp**. The config `default_if_untestable: bp` follows
  the table, not step 4. For the "slope not significant, range >= 10%" case both say USD.
- "BTC specifically" says the value comes from "step 2", but the unit comes from step 4.
- Does the regression also run for FX? The table fixes FX in pips; step 4 says the unit for "the
  extrapolated period" in general. USDJPY ran 76 to 160, so bp versus pips changes 2011 to 2015
  USDJPY costs by about 35%.
- "Profile of the first 12 archived months" is not defined. It could be the median of all ticks
  in 12 months per hour-of-week bucket, the mean or median of 12 monthly medians, or a
  month-by-month mapping. Its bp conversion price is also undefined (the 12-month mean price? each
  month's own?).
- *Failure scenario:* NAS100 has 8.5 of its 13 historical years (about 65%) costed from Aug 2019
  to Jul 2020, a window containing the March 2020 crash. Under bp-of-price the 2011 NAS100 spread
  (index ~2,200) is about 3.5x smaller in points than under fixed points. The two readings give
  very different NAS100 net results.

### M-8. The unit regression is statistically unsound and uses exposed-period data (3.4 step 4, A-10)
OLS on monthly time series of spread and price, where both trend over a decade, gives spurious
|t| > 3 almost always. Residuals are serially correlated and no HAC or differencing is specified.
A **negative** significant slope (spreads tightened while BTC price rose) also passes "|t| > 3"
and would choose bp, which is the opposite of what the reasoning intends. The regression runs on
the full archive through Nov 2026, including the exposed period. That data is not used to select
signals, but it is future information for a 2011 to 2015 cost model.

### M-9. Hour-of-week monthly median spread understates cost at the moment of these signals (3.4 step 2)
Sweeps and reclaims cluster at news releases, session opens and the Sunday reopen, which are the
times spreads widen. A tick-count median over a whole hour-of-week bucket for a month is the
typical spread, not the spread conditional on a sweep. The archive has tick-level bid and ask, so
a spread at (or a percentile around) the actual fill timestamp is available for archived months.
The spec chose the median without saying why.
- *Failure scenario:* an NFP-minute EURUSD M5 reclaim pays a costed 0.8 pip when the archive
  shows 2 to 3 pips at that minute. The bias has one sign (in favour of the strategy) and is
  concentrated in the M5 cells with the smallest R. The multiplicative 1.5x pass bar does not
  necessarily cover a spike conditional on the event.
- Minor variant: the monthly bucket includes ticks **after** the trade (later in the month). That
  is small look-ahead, and it feeds into the minimum-stop eligibility decision.

### M-10. Slippage is fixed in absolute price across a 4x to 30x price history (3.4, A-14, config)
BTC $5 per side is 15.6 bp at $3,200 (2018) and 0.4 bp at $120,000. Gold $0.05 is 0.48 bp at
$1,050 and 0.13 bp at $4,000. NAS100 0.5 pt is 2.3 bp at 2,200 and 0.24 bp at 21,000. Section 3.1
and the BTC cost paragraph explicitly reject fixed-USD sizing for exactly this reason, and then
slippage uses it. Early-sample costs are relatively high and late-sample costs relatively low,
which interacts with the by-year criterion (7.3) and the exposed-period criterion (7.8).
- Config units are fragile: `slippage_per_side: XAUUSD: 0.5  # pips` relies on pip_size 0.1 to
  mean $0.05. Someone reading the spec's "$0.05" against the config's "0.5" can get 10x.

### M-11. Signal feed is not the execution feed; the Binance "bid" is a trade price (1, 3.2 "All prices are bid", 3.4 step 5)
- Binance M1 klines are **trade** prices, not bid. The spec treats them as bid, sets ask =
  Binance + Exness spread, and triggers short stops "on the bid". With Exness BTC spread at about
  20 bp in 2018 (data doc) and BTC p_min at 5 bp, the sweep test is smaller than the half-spread
  difference between a trade print and the bid.
- BTCUSDT is not BTCUSD. In Oct 2018 the USDT discount of several percent moved levels relative
  to the USD quote. HistData NSXUSD and EURUSD bids are not Exness quotes either. A 1-pip p_min
  sweep on HistData may not exist on Exness.
- None of this is quantified, and there is no pre-registered check (e.g. on overlapping archive
  months, the share of HistData sweeps that also sweep on the Exness bid).

### M-12. Swap pass bar (S1) is not shown to be conservative for the period (3.4 swap, 7.5, A-11)
S1 applies an "adverse" 3%/year of price on FX in both directions. Actual broker swap is the rate
differential plus a markup. In 2022 to 2026 the USD rate was about 4 to 5.5%, so the
carry-paying side of USDJPY, EURUSD and GBPUSD likely cost more than 3%/year plus markup. S1 is a
**pass** criterion, so an understated S1 can let a cell pass. Also, rollover is fixed at 22:00
UTC, but the NY-17:00 rollover is 21:00 UTC in US summer, so nights held are miscounted for
trades spanning 21:00 to 22:00. The triple day for gold and indices is not necessarily Wednesday
at every broker.

### M-13. Test sidedness and the Romano-Wolf construction are unspecified (4.3, 4.4, 7.1)
Bonferroni |t| >= 3.31 is **two-sided** 0.05/54. Criterion 7.1 is directional ("> 0 with RW p <
0.05"). If RW is run one-sided at 5% FWER, its implicit bar is about 3.11, looser than the
"reference". Also unspecified:
- RW null-centring (subtract the sample mean from the bootstrap draws?) and studentisation. The
  SE and the null distribution come from the same 10,000 draws, with no double bootstrap.
- How cells with zero trades in a resampled set are handled.
- t = mean per trade while resampling weeks: a ratio estimator with a random denominator.
Two analysts can report different adjusted p-values from the same trades.

### M-14. Deflated Sharpe: the input and the trial count are both choosable (4.4, 7.7, A-16)
A-16 reports two Sharpes (per-trade R and annualised daily). 7.7 does not say which one feeds
DSR, so the more favourable one can be chosen after the fact. DSR also needs the variance of
Sharpe across trials, skew and kurtosis. With 54 nested, correlated cells that variance is small,
and "54 trials" both overstates independence and understates the search. H002 was designed after
H001's 13,824-config walk-forward search and the H001 diagnostics on the **same** 2011 to 2023
data (4.1 and 4.6 say so). The effective number of trials behind this hypothesis is larger than
54, and DSR > 0.95 at N = 54 overstates significance.

### M-15. The primary family is largely underpowered by the spec's own numbers (4.6, 7.2)
4.6 expects PWH/PWL at 330 to 520 setups per FX instrument for 2011 to 2023, then "possibly cut
by half" (165 to 260), and 160 to 260 for BTC before cuts. 7.2 requires at least 400 executed
trades. So most of the 18 PW tests are expected to be "insufficient evidence" before any data is
run, yet they still count in the 54 used for Bonferroni, RW and DSR, which makes the EQ tests
harder. 80% power at E = 0.30 needs 574 trades. A 400-trade cell can only pass Bonferroni with an
observed E >= 0.29R, which is close to the hoped-for effect.
- *Failure scenario:* a true +0.25R edge has about 20 to 30% power at 400 trades. A "fail" is
  mostly uninformative, and a pass is likely to be an overestimate (winner's curse). The spec
  should state the expected number of cells reaching 400 and what "insufficient evidence" implies
  for the hypothesis as a whole.

### M-16. Placebo design does not isolate the level effect, and one placebo uses ex-post information (4.5, 7.6, A-17)
- **Random offset:** u ~ U(-0.5, 0.5) puts half the "high" placebos *inside* the previous week's
  range, between EQ and PWH, often below the current price at Monday 00:00. The first candle then
  "sweeps" them by construction, which is a different mechanism from a sweep of an untested high.
  Values of u near 0 reproduce the real level, which contaminates the null. The spec does not say
  whether u is shared by the PWH and PWL placebos of a week or drawn separately (shared draws make
  the two sides dependent). Placebo trade counts differ from the real cell, and a 95th percentile
  of 200 expectancies is a noisy threshold (Monte Carlo SE of about ±1.5 percentile points).
- **Unequal pivots:** "single confirmed H1 pivots that are not in any cluster". If membership is
  judged over the whole sample, a pivot that will join a cluster *later* is excluded from the
  placebo *now*. That is look-ahead in the placebo set. It must be "not in a cluster at signal
  time". "Same age limit" for a singleton (5 trading days from its own confirmation?) is not
  defined.
- **Stale levels** have no pass rule. PW and EQ use different placebo criteria (percentile versus
  bootstrap-CI difference), and the 18 PW placebo tests and 36 EQ placebo tests have no
  multiplicity treatment. That is acceptable only because they are conjunctive, and the spec
  should say so.

### M-17. Choices left open after "freeze" (header, 3.4 step 1, 4.9, config `fallback_floor`, `unit_for_extrapolation: tbd`, `scenario_s3: pending`)
- 4.9 requires the independent review **before freeze**, but the spec and config are already
  marked frozen. Any fix from this review is a v0.6 by the spec's own rule.
- The Standard suffix is "pending", and if the demo shows another suffix, "that series is used
  instead". The data doc already shows the medians of every variant (`_Standart_Plus` 1.1, `m`
  0.8, plain 0.6 pip), so the series is chosen after costs are visible.
- The config's `fallback_floor ... only if archive unavailable` has no trigger definition. It
  does not cover a partially missing month, a corrupt zip, or "unavailable" for one instrument.
  It is not in spec 3.4 at all, which only mentions H001 floors for the comparison run. That gives
  a switch between two cost models.
- The unit output (`tbd`) and S3 (`pending`) are to be written into a config whose hash is
  supposedly frozen at 9cf9556.

---

## Minors

| # | Section | Issue | Failure scenario |
|---|---|---|---|
| m-1 | 2.3, A-2 | The PWH/PWL used for EQ premium/discount when the sweep candle and the reclaim candle fall in different weeks (Sunday 23:55 sweep, Monday 00:10 reclaim) is unspecified: the sweep week, the reclaim week, or the cluster's formation week? | The same EQL is aligned under one reading and neutral under another. |
| m-2 | 3.2, 2.2 | The first candle eligible to sweep a new level is not stated (the candle *opening* at or after the availability time). Boundaries coincide for UTC-aligned TFs, so the effect is small, but test 6 covers visibility, not sweep eligibility. | An off-by-one candle on the confirmation bar. |
| m-3 | 3.2, 6 test 15 | Window "in candles" versus wall-clock deadline: near a session close, or with missing M5 candles, the 12-candle count and the 60-minute deadline differ. Test 15 is phrased in candles. | A Friday 20:55 sweep has 1 real candle in its window; a candle-count implementation looks into Sunday. |
| m-4 | 3.3 | Minimum-stop rule: which hour's spread, and is slippage at sensitivity values used? | Borderline setups flip. |
| m-5 | 3.3 | Target touch versus trade-through (>= vs >) is unstated. | Win/loss flips on exact touches. |
| m-6 | 4.7 | Depth buckets stop at 1.0 ATR, but the extreme (a wick) can exceed L + 1 ATR without consumption; body with high == low divides by zero; "ATR14" TF unstated for close distance; D1 bar definition (the UTC day includes a Sunday stub for FX) unstated; trend tie (difference = 0) and "close 4 weeks earlier" (t-4 or t-5) unstated. | Descriptive tables differ between implementations. |
| m-7 | 4.2 stage 1 | The "same-hour-of-week mean" baseline is computed over the full sample, so it is look-ahead within a descriptive statistic. | None for pass/fail; mislabelled as measured evidence if reported as [E] without caveat. |
| m-8 | 7.3, 11 I-3 | 7.3 still reads "BTC 5 of 7"; I-3 and config say 4 of 6 (2018 to 2023). | Ambiguous pass rule for BTC. |
| m-9 | 4.6, 7.2 | 4.6 applies "below 400 → insufficient" to PWH/PWL cells only; 7.2 applies 400 to all cells. | EQ cells with 300 trades treated differently. |
| m-10 | 7.3 | Year attribution (entry or exit time) and years with zero trades (count as not positive?) are unstated. | A cell with 8 positive years and 1 empty year passes or fails. |
| m-11 | 4.1 | Exposed-period end "latest" is not fixed, so the run date is a free choice. | Run stopped at a convenient month. |
| m-12 | config header | Says "FINAL DRAFT, NOT FROZEN ... frozen only after collins approves" while `status: frozen`. | Audit confusion over which file is binding. |
| m-13 | header, 3.4, data doc | Mixed date conventions: freeze "2026-11-25 22:58 UTC" precedes approvals and decisions dated "26 Nov" (A-1 to A-23, I-1 to I-3, archive check). The gold tick is "26 Nov 00:08 Nairobi" in the spec and "25 Nov" in the data doc. The spec says all timestamps are UTC. | The audit trail cannot show that every approval predates the freeze. |
| m-14 | 1 | HistData "fixed EST, no DST" is an unverified premise (test 1 checks only the arithmetic). If the files are in New York time with DST, weekly and monthly boundaries and session buckets shift by 1 h for about 34 weeks a year. | Sunday-evening bars assigned to the wrong week. |
| m-15 | 4.4 | The stationary bootstrap over "weeks" for instruments with different calendars (BTC 7-day weeks, starts 2017) is unspecified: one index for all 54 cells including pre-2017 weeks with no BTC trades? | Different SEs for BTC cells. |
| m-16 | 8 | Kill rule "backtest's 5th-percentile path" is undefined (bootstrap of trades? of weeks? which cost model?). | The kill decision is choosable later. |
| m-17 | config vs spec | The config does not encode several reported sensitivities that the spec promises: zero-width neutral band (A-20), `levels_degraded` exclusion, run under H001 cost floors, archived-versus-extrapolated split. | Omitted or changed without a config diff. |

---

## Look-ahead checklist (requested items)

| Item | Verdict |
|---|---|
| PWH/PWL, PMH/PML levels | OK (previous completed period, usable from the boundary; tests 3 and 4). Expiry while swept: M-1. |
| Pivots | OK (confirmed at the close of i+3, test 6). |
| ATR | OK as indexed (i+3; c-1 for consumption; reclaim candle for the buffer). Construction underspecified: M-5. |
| Cluster membership | Real-time formation OK; ambiguous rules B-3. The unequal-pivot placebo is look-ahead if membership is judged ex post: M-16. |
| Premium/discount | Uses the current week's PWH/PWL: OK. Week choice across a boundary: m-1. |
| Spread profiles | Same-month buckets include later ticks (M-9); the first-12-month profile for 2011 to 2015 is future data by design (acknowledged); the regression uses data through 2026 (M-8). Eligibility via the minimum-stop rule inherits this. |
| Normal-hours derivation for the gap rule | **Look-ahead**: it uses the whole year's data to decide scorability (B-2). |
| Regime buckets | Trailing, OK; definitions loose (m-6). |
| Unit regression | Uses future and exposed data, and is spurious (M-8). |
| End-of-week "last M1 bar" | Determined from data in hindsight (B-1). |
| Data-gap exclusion | Window depends on exit time, so selection on outcome (M-6). |
