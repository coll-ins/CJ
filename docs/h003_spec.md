# H003 pre-registration: time-series momentum (trend), daily, vol-scaled

Version **v0.1 PROPOSED, 2026-11-26. NOT frozen, NOT run.** No H003 backtest, signal statistic or
P&L has been computed on any data. Nothing in this file may be changed after a run except by a new
version that collins approves. Evidence labels as in H002: [E] verified here, [H] published
research, [U] unverified assumption, [B] backtest result (none yet).

Naming: the old M5 breakout-fade draft ("H003-candidate") is renamed **H004-candidate**
(`docs/h004_candidate_m5_breakout_fade.md`, contents unchanged). This file is H003.

---

## 0. Bottom line before you sign

* H001 and H002 failed for one shared reason: price levels carried no information, and on M5-H1
  the spread (0.10-0.17R per trade in H002) ate whatever was left. H003 changes **both** things:
  the signal source (past return over weeks/months, not levels) and the holding period (weeks, so
  spread becomes a few % of the move instead of 10-20%).
* Trend following is the best-documented directional signal in the public literature. It is also
  **weak on a single instrument**, decayed after publication, and its biggest cost at a retail CFD
  broker is **swap**, not spread. H002 could omit swap; H003 cannot, because positions are open
  almost every night.
* **Power is the real problem, not the idea.** A t-stat grows with years, not with trades:
  t ≈ annual Sharpe × √years. With realistic single-instrument net Sharpe of 0.3-0.5, the chance
  of clearing the bar is 12-42% for FX (24 years), 6-24% for gold/NAS100, 3-8% for BTC (section 6).
  The most likely outcome even if trend is real is "insufficient evidence" on most instruments.
  I am telling you this now so a null result is not a surprise and is not read as "trend is fake".
* What makes it worth running anyway: FX data **2000-2010 has never been used** by this project
  (H001/H002 started 2011), so for EURUSD, GBPUSD and USDJPY 11 of 24 evaluation years are clean.

---

## 1. Candidate signal families considered

| # | Family | Published evidence | Fit to our 6 instruments and Exness costs | Verdict |
|---|---|---|---|---|
| A | **Time-series momentum / trend** (sign of past 1-12 month return, vol-scaled position) | Moskowitz, Ooi, Pedersen (2012, JFE 104(2)) [H]: positive TSMOM in all 58 futures/forwards incl. currencies, equity indices, metals, 1985-2009. Hurst, Ooi, Pedersen (2017, JPM, "A Century of Evidence on Trend-Following Investing") [H]: blended 1/3/12-month trend positive in every decade since 1880 at portfolio level. Liu & Tsyvinski (2021, RFS 34(6)) [H]: time-series momentum in BTC at daily/weekly horizons. **Against:** Huang, Li, Wang, Zhou (2020, JFE 135(3)) [H]: asset-by-asset regressions show *little* evidence of TSMOM in- or out-of-sample; the strategy's profit is close to that of a rule using only the historical mean. McLean & Pontiff (2016, JF) [H]: anomaly returns fall ~1/3 out of sample and more after publication. | Works on all 6. Daily bars, multi-week holds, so spread is small. Swap is large and must be modelled. Per-instrument power is low (section 6). | **Recommended** |
| B | **FX fixing / time-of-day flow** (USD appreciates into the Tokyo/ECB/London fixes, depreciates after; "W" shape) | Krohn, Mueller, Whelan (2024, JF 79(1), 541-578) [H], 9 USD pairs, 5-min data. Breedon & Ranaldo (2013, JMCB) [H]: currencies weaken in their domestic trading hours. | EURUSD, GBPUSD, USDJPY only (3 of 6). Intraday, so spread is back to being a large share of the move: the same failure mode as H001/H002. Effect size per day vs the 0.7-0.8 bp Exness round trip not yet checked against the paper [U]. More observations do **not** raise t unless annual Sharpe is higher (t depends on years, not trade count). | Alternative. Reasonable second study, worse fit to "spread small relative to trade". |
| C | **FX carry** (long high-yield, short low-yield currency) | Lustig, Roussanov, Verdelhan (2011, RFS); Menkhoff, Sarno, Schmeling, Schrimpf (2012, JF) [H]. | It is a *cross-sectional* trade across 10-40 currencies; with 3 USD pairs it does not exist in testable form. At Exness, carry is paid as swap net of broker markup, which we cannot yet measure (section 4.3). Gold, BTC, NAS100 have no carry in this sense. | Rejected |
| D | Volatility as a signal (vol-managed exposure) | Moreira & Muir (2017, JF) [H]. Kim, Tse, Wald (2016, JFM) [H]: much of TSMOM's Sharpe comes from vol scaling. | Not a direction signal on its own. Used **inside A** as the position-sizing rule, and isolated as a diagnostic (4.6). | Folded into A |

Sources: [Huang et al. 2020](https://econpapers.repec.org/RePEc:eee:jfinec:v:135:y:2020:i:3:p:774-794),
[Krohn, Mueller, Whelan 2024](https://econpapers.repec.org/RePEc:bla:jfinan:v:79:y:2024:i:1:p:541-578),
[Liu & Tsyvinski 2021](https://econpapers.repec.org/RePEc:oup:rfinst:v:34:y:2021:i:6:p:2689-2727.).
Moskowitz-Ooi-Pedersen 2012, Hurst-Ooi-Pedersen 2017, McLean-Pontiff 2016, Moreira-Muir 2017 are
cited from memory [H, not re-fetched here]; exact figures from them are not used anywhere in the rules.

Why the 12-month-only rule of MOP is not used alone: Huang et al. show the single 12-month rule is
fragile asset by asset. The 1/3/12-month blend (Hurst et al.) is the standard practitioner version
and is pre-specified here so there is **one** rule per instrument, not a lookback search.

---

## 2. Instruments, data, periods

| Instrument | Signal data | Evaluation period (may qualify) | Exposed period (can only disqualify) | Clean (never used by H001/H002) |
|---|---|---|---|---|
| EURUSD | HistData M1 bid | 2000-01 to 2023-12 | 2024-01 to 2026-11 | 2000-2010 |
| GBPUSD | HistData M1 bid | 2000-01 to 2023-12 | 2024-01 to 2026-11 | 2000-2010 |
| USDJPY | HistData M1 bid | 2000-01 to 2023-12 | 2024-01 to 2026-11 | 2000-2010 |
| XAUUSD | HistData M1 bid | 2009-03 to 2023-12 | 2024-01 to 2026-11 | none |
| NAS100 | HistData NSXUSD M1 (proxy for Exness USTEC, A-18 of H002) | 2010-11 to 2023-12 | 2024-01 to 2026-11 | none |
| BTCUSD | Binance 2017-08-17..31, Exness BTCUSDm bid from 2017-09 (as H002 v0.6) | 2017-08 to 2023-12 | 2024-01 to 2026-11 | none |

HistData first available year checked from its download index on 2026-11-26 [E]: EURUSD, GBPUSD,
USDJPY 2000; XAUUSD 2009; NSXUSD 2010. The first 252 trading days of each series are warm-up
(no position). Each instrument is reported on its own; **never pooled** (section 7 note on a
descriptive portfolio).

Honesty on "exposed": 2011-2023 has been looked at by H001/H002, but only through level/sweep
rules; no trend statistic has been computed. Trend-following performance over 2011-2023 is,
however, public knowledge (weak 2011-2019, strong 2022) [U from industry indices], so this period is
not blind in the literature sense. 2000-2010 FX is the cleanest data we have.

---

## 3. Rules (one rule per instrument, no grid)

### 3.1 Daily bar
* Day boundary: **17:00 America/New_York**, DST-aware via tz database, never hardcoded (same as H001).
  HistData is fixed EST (UTC-5, no DST); convert to UTC first.
* Daily close C_d = bid close of the last M1 bar at or before 17:00 NY. Days with < 50% of normal
  M1 bars are flagged; if the close bar is missing, the day is skipped (no signal update).
* Weekend bars (BTC trades 7 days): BTC uses the same 17:00 NY boundary, 7 days a week; lookbacks
  in calendar-scaled days (3.2).

### 3.2 Signal
For lookbacks L ∈ {21, 63, 252} trading days (BTC: {30, 91, 365} calendar days):

    s_L(d) = sign(C_d / C_{d-L} - 1)          (0 if exactly 0)
    S(d)   = (s_21 + s_63 + s_252) / 3        ∈ {-1, -1/3, +1/3, +1}

### 3.3 Position size (vol scaling)
* σ̂(d) = EWMA of squared daily close-to-close log returns, centre of mass 60 days (MOP 2012),
  annualised with √261 (BTC √365).
* Target notional as a fraction of equity: w(d) = S(d) × σ* / σ̂(d), σ* = **10% annualised per
  instrument** for the statistical test. (Scale does not change any t-stat; it changes only swap/
  cost in currency, which scale linearly too. Live sizing is a Phase 3 decision, see D-4.)
* Leverage cap |w| ≤ 4 (FX), 2 (XAU, NAS100), 1 (BTC). Cap binding days are reported.

### 3.4 Execution
* Signal computed at the day close. Execution at the **first M1 bar at or after 03:00 NY** the next
  trading day (around the London open), to avoid the rollover spread spike at 17:00 NY.
  Fill price: bid + spread for buys, bid for sells, + slippage (4.2).
* No-trade band: trade only if S changes, or |w_target − w_held| > 25% of |w_target|.
* **No stop loss and no profit target** in the primary rule. Exit only through S going to the other
  side or the size band. (Trend rules with stops are a different hypothesis; see D-3.)
* Overnight holding is the whole point: positions span weekends.

### 3.5 Return measured
Daily net return r(d) = w × (C_d / C_{d-1} − 1) − spread/slippage cost on trade days − swap
accrued that night (4.3). All statistics use the daily net return series.

---

## 4. Costs

### 4.1 Spread [E source, U pre-archive]
Exness tick archive, Standard `m` series (EURUSDm, GBPUSDm, USDJPYm, XAUUSDm, BTCUSDm, USTECm),
median spread by month and hour-of-week, at the execution minute. Before archive coverage (FX/gold
before 2015-08, NAS100 before 2019-08): first 12 archived months, tagged *extrapolated*, **× 1.5**
for 2000-2007 (spreads were wider) [U]. Sensitivity: × 3 on all pre-archive spread.

### 4.2 Slippage [U]
Same as H002 v0.6 (fixed per instrument), sensitivities 2× and 4×.

### 4.3 Swap: primary, not omitted [U, needs data]
A trend position is open ~90%+ of nights, so swap is first-order. Model:

    swap_long  per night = notional × (r_base − r_quote − m) / 360
    swap_short per night = notional × (r_quote − r_base − m) / 360
    ×3 on the broker's triple-swap weekday (Wednesday for FX/gold/indices; BTC daily, no triple) [U]

* r = overnight policy/interbank rate per currency (USD, EUR, GBP, JPY), daily 2000-2026.
  Gold: r_base = 0 (gold lease rate ignored). NAS100: r_base = dividend yield, primary 1.0% flat [U].
  BTC: no rate; swap = −m both sides.
* m = broker markup. Primary **m = 2.0% per year each side** [U]. Calibrated, once collins sends
  Exness MT5 *Specification* swap values for the 6 symbols, as m = (rate differential today −
  Exness swap today). If calibration differs from 2.0% by more than 1 point, the calibrated value
  replaces it **before** the run (that is a pre-run change, allowed).
* BTC: Exness crypto swaps are known to be large [U]; primary m for BTC = **calibrated value
  only**. If no calibration arrives, BTC is run at m = 10%/yr and labelled "cost unknown".
* Sensitivities: m = 0.5%, 2%, 4%; and swap-free (m and r both 0), reported if collins's account is
  eligible for Exness swap-free status (to check, D-5).
* **Data blocker:** FRED, ECB, BoE, NY Fed and BoJ are all unreachable from the cloud environment
  (checked 2026-11-26 [E]). Need one of: add `fred.stlouisfed.org` to the environment's allowed
  hosts (preferred, one source for all four currencies), or fetch the series on collins's computer.

### 4.4 Costs reported separately
Gross, spread only, spread + slippage, + swap. So a failure can be attributed.

---

## 5. Test family and evidence bar

**Primary family: 6 tests** (one blended rule × 6 instruments). Two-sided α = 5%, Bonferroni
|t| ≥ **2.64**; Romano-Wolf step-down over the 6 also reported. (If you want the three lookbacks as
separate tests instead, the family is 18 and the bar |t| ≥ 2.99, which lowers power further.)

t-statistic: mean daily net return / Newey-West SE (lag 21 trading days), plus a stationary block
bootstrap (mean block 21 days, 10,000 draws) as a check. If they disagree on pass/fail, the stricter
one wins.

An instrument **passes** only if all of these hold on the evaluation period:

1. Net mean > 0 and |t| ≥ 2.64 (Newey-West and bootstrap).
2. Positive net return in ≥ 60% of calendar years (FX ≥ 15 of 24, XAU ≥ 9 of 15, NAS ≥ 8 of 13,
   BTC ≥ 4 of 6).
3. Beats both benchmarks with bootstrap p < 0.05 on the difference:
   (a) **sign-scramble placebo**: same position sizes, signal signs drawn by block permutation;
   (b) **historical-mean rule** of Huang et al. 2020: sign of the expanding-window mean return,
   same vol scaling. If TSMOM does not beat (b), the "trend" is just long-run drift.
4. Still positive at: spread × 1.5, slippage × 2, swap m = 4%.
5. Long-side and short-side contributions both ≥ 0 **or** beats a vol-scaled buy-and-hold of the
   same instrument (needed for NAS100/gold/BTC, where up-drift can masquerade as trend).
6. Deflated Sharpe > 0.95 counting all trials run in this project (13,824 + 54 + 6 = 13,884).
7. Exposed period 2024-01 to 2026-11 net mean ≥ 0 (cannot qualify, can disqualify).
8. Max drawdown and longest underwater period reported; no threshold (descriptive).

A pass means: **eligible for a forward demo on Exness**, nothing more. Live money needs a separate
authorisation, as for H001/H002.

---

## 6. Power (computed before any data is touched)

t ≈ annual net Sharpe × √years. Probability of t ≥ 2.64 for a given true Sharpe:

| Instrument | Years | SR 0.3 | SR 0.5 | SR 0.7 | SR 1.0 |
|---|---|---|---|---|---|
| EURUSD / GBPUSD / USDJPY | 24 | 12% | 42% | 79% | 99% |
| XAUUSD | 14.8 | 7% | 24% | 52% | 89% |
| NAS100 | 13 | 6% | 20% | 45% | 83% |
| BTCUSD | 6.3 | 3% | 8% | 19% | 45% |

Years needed to reach t = 2.64 on average: SR 0.3 → 77 y, 0.5 → 28 y, 0.7 → 14 y.

What Sharpe to expect: single-asset trend Sharpe in the literature is roughly 0.2-0.5 gross
[H, approximate], diversified portfolios 0.7-1.0; post-publication decay (McLean-Pontiff) and swap
cut that further. **Expected result: insufficient evidence on most instruments, possible pass
only on an FX pair with a strong 2000-2010 period.** BTC cannot realistically pass and is run for
description; I recommend keeping it in the family anyway so the bar does not change if it is dropped
later (D-2).

"Trades per market": with a 25% band and a three-part blended signal, expect roughly 15-40
rebalance trades a year per instrument [U, to be counted from signal data only, before P&L, and
reported in the run]. Trade count is not the sample size here; independent years are.

---

## 7. Diagnostics (reported, outside the family, cannot qualify anything)

* Each single lookback (21/63/252) per instrument.
* Signal without vol scaling (fixed notional), to separate trend from vol timing (Kim-Tse-Wald).
* **Volatility-expansion split (collins, 26 Nov):** trend daily net return split by regime known at
  the signal close: σ_5d / σ_60d > 1.25 (expanding), < 0.8 (contracting), else neutral. Also Donchian
  20-day breakout days after the 20-day range was in its lowest quintile of the past year
  ("squeeze breakout"), direction = breakout side. Descriptive only, outside the family; if it looks
  useful it becomes its own pre-registered hypothesis (H005-candidate), never a filter added after
  seeing results.
* Results by sub-period: 2000-2010 (clean), 2011-2023, 2024-2026.
* An equal-risk portfolio of the 6 is computed **descriptively only**, because you ruled out
  pooling. It is the version of trend following the literature actually supports; it cannot qualify
  any instrument. Say if you want it dropped (D-6).

---

## 8. Decisions needed from collins before freeze

* **D-1** Approve family A (trend) as H003, B (FX fixing) parked as a later candidate.
* **D-2** Family = 6 blended tests, |t| ≥ 2.64 (recommended) vs 18 tests, |t| ≥ 2.99.
* **D-3** No stop loss in the primary rule. This departs from the project's "0.5% risk per trade
  with a stop" convention: risk is controlled by vol targeting, not stops. Live mapping (D-4).
* **D-4** Live sizing later: proposed risk unit = ex-ante 1-day σ of the position; 0.5% of equity
  ≈ 2.3σ one-day loss at σ* ≈ 3.4% annual per instrument. Not needed for the test.
* **D-5** Swap data: (a) add `fred.stlouisfed.org` to allowed hosts (link: Project settings →
  environment network), (b) MT5 Specification screenshot of swap long/short and triple-swap day
  for EURUSDm, GBPUSDm, USDJPYm, XAUUSDm, BTCUSDm, USTECm; (c) whether your account shows
  swap-free status.
* **D-6** Keep the descriptive 6-instrument portfolio (recommended) or drop it.
* **D-7** Accept that 2011-2023 is not literature-blind and that only 2000-2010 FX is clean.

After sign-off: freeze hash recorded in `docs/h003_frozen.md`, unit tests on synthetic series, then
one run. No parameter in sections 3-5 changes after the run.
