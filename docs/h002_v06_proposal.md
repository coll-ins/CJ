# H002 v0.6 proposal: answers to the independent review

Status: **PROPOSED, needs collins's approval.** v0.5 stays the frozen record until then.
Nothing has been coded or run. The review is `docs/h002_independent_review.md` (38 findings:
4 blockers, 17 majors, 17 minors). I checked every blocker against the spec text and agree
with all four; they are real defects, not wording.

Each fix below is the narrowest one I can see. None was chosen by looking at any H002
outcome (none exist).

## Blockers

| # | Problem (verified) | Proposed v0.6 rule |
|---|---|---|
| B-1 | Under the Monday 00:00 UTC week the "last M1 bar of the week" for FX/gold/NAS100 is Sunday night, so trades would be held through the weekend gap; the short exit fill also omits the spread. | **Weekly flat time, fixed clock, known in advance:** FX, gold, NAS100 close any open trade at the open of the **Friday 20:00 UTC** M5 bar (earliest Friday close across DST is 21:00 UTC). No new entries from Friday 20:00 UTC until Monday 00:00 UTC; sweeps/reclaims in that window are logged `weekend_window`, not traded (Sunday-evening bars still build the ending week's high/low, A-2). BTC: flat at Sunday 23:55 UTC. Exit fills: long at bid − slippage, short at bid + spread + slippage. |
| B-2 | I-1's "normal hours from data, 50% of weeks, per UTC minute-of-week" cannot follow DST-shifting sessions (false gaps every winter) and uses the same year's future data. | Normal hours = minute-of-week **in America/New_York time**, share of weeks with a bar ≥ 50%, computed from the **previous calendar year** only (2011 uses 2011 itself, flagged). |
| B-3 | EQH/EQL cluster rules can be implemented several ways. | (a) Tolerance measured against the cluster's **current level** (its most extreme pivot), no chaining; (b) the dead-pivot check uses the level including P; (c) a pivot that exceeds an active cluster's level by ≥ p_min is a **sweep** of that cluster, never a member and never the seed of a new cluster at that price until the old cluster is retired; (d) a pivot belongs to at most one cluster; a member within tolerance and above the level by < p_min raises the level; (e) trading days counted on UTC dates Mon–Fri (Sunday bars count as Monday) for FX/gold/NAS100, all dates for BTC; expiry at 00:00 UTC after the 5th trading day. |
| B-4 | Stop/target triggers and fills ambiguous on the short side; stop slippage unstated. | One fill table. Ask = bid + spread of that bar's month/hour bucket. **Long:** entry ask + slip; stop triggers bid ≤ stop, fills stop − slip (gap: bar open bid − slip); target triggers bid ≥ target, fills target. **Short:** entry bid − slip; stop triggers ask ≥ stop, fills stop + slip (gap: bar open ask + slip); target triggers ask ≤ target, fills target. Touch counts (≥ / ≤). Stop price = sweep extreme ± (0.1 × ATR) ± spread as approved. |

## Majors

| # | Proposed v0.6 rule |
|---|---|
| M-1 | A level swept before it expires keeps its window to the 60-minute deadline. "Gap sweep" = first bar after a ≥ 30-minute data closure opening beyond the level. |
| M-2 | Same source, same reclaim candle: one trade, on the level with the earliest sweep; the others are retired as `signalled_not_executed`. Signals while a position is open: logged and retired (their one attempt is used). |
| M-3 | The executed trade list is fixed under the primary cost model. Sensitivity runs re-price that same list; they never re-select trades. Small-stop skips are reported with their hypothetical R. |
| M-4 | Entry bar opens beyond the stop or target → not taken, logged `entry_beyond_stop` / `entry_beyond_target` with hypothetical R. |
| M-5 | ATR14 Wilder: seed = mean of first 14 true ranges; only bars that exist (no empty bars); true range uses the previous existing bar's close, also across weekends. |
| M-6 | A `data_gap` trade still blocks later signals until its gap ends; the share of unscorable events is reported per cell and flagged if above 2%. |
| M-7 + M-8 | **Drop the unit regression.** Pre-archive costing: per hour-of-week bucket, the **median of the first 12 archived months' bucket medians**; FX applied in pips, gold/BTC/NAS100 converted to bp of the same 12 months' mean mid and applied in bp. Stale v0.4 export text removed. |
| M-9 | Primary spread = the **previous month's** bucket median (strictly prior data). Added sensitivity: previous month's bucket **p90** (now recorded). |
| M-10 | Gold/BTC/NAS100 slippage converted to bp at today's values: XAUUSD 0.14 bp, BTCUSD 0.56 bp, NAS100 0.25 bp; FX stays 0.2 pip. 2x/4x sensitivity unchanged. Config units written explicitly. |
| M-11 | Stated limitation: HistData bid and Binance BTCUSDT trade prices are not the Exness feed. Option for collins (not assumed): use Exness BTCUSDm bid ticks for BTC signals from Sep 2017, since that is the instrument traded. **Recommendation: yes for BTC only**; FX/gold/NAS stay on HistData as decided. |
| M-12 | Rollover at 17:00 New York (DST-aware), triple swap Wednesday. S1 kept as approved; break-even swap remains the headline number. |
| M-13 | Two-sided tests throughout. Romano-Wolf on studentised statistics, centred bootstrap; consistent with the |t| ≥ 3.31 reference. |
| M-14 | Deflated Sharpe on per-trade R, fixed now. Reported twice: 54 trials, and 54 + 13,824 (H001's search on the same data). |
| M-15 | Acknowledged, no rule change: family stays 54 (conservative). Every fail is reported with its power at +0.25R so "fail" is not read as "no effect". |
| M-16 | Random-offset placebo: L' = PWH + u·R and PWL − u·R with u ~ U(0.1, 0.5), independent draws per side (always outside last week's range, never on the real level). Unequal-pivot placebo: pivots not in any cluster **at their confirmation time**. Stale levels: descriptive only. |
| M-17 | Fallback floor used only for a month the archive cannot serve, logged per month. S3 optional (needs screenshots). Suffix: the review is right that I can decide this from data: `m` series spreads match the Standard/Cent pattern; kept, with collins's confirmation still welcome. |

## Minors (wording or audit trail; fixed in v0.6 as stated)

m-1 premium/discount uses the PW range of the **reclaim** candle's week; m-2 first eligible sweep candle = first candle opening at or after availability; m-3 the window is wall-clock 60 minutes, missing candles do not extend it; m-4 minimum-stop uses the reclaim hour's spread and primary slippage; m-5 touch = fill (B-4); m-6 depth buckets get "≥ 1.0" as a 4th bucket, zero-range candles are their own bucket, ATR of the confirmation TF, D1 = UTC day, trend compares week t−1 close with week t−5 close, tie = "against"; m-7 stage-1 baseline from prior data only; m-8 7.3 corrected to BTC 4 of 6 (2018–2023); m-9 the 400-trade floor applies to all cells; m-10 year = entry year, a year with zero trades counts as not positive; m-11 exposed period ends 2026-11-13 (last HistData FX bar) for all instruments; m-12 config header fixed; m-13 all record times in UTC, with the order of approvals listed; m-14 a unit test checks a known HistData Sunday open against the 22:00 UTC (winter) / 21:00 UTC (summer) FX reopen to prove the fixed-EST premise; m-15 one weekly bootstrap index for all cells, BTC cells resample only weeks from 2017-08-17; m-16 kill path = 5th percentile of 10,000 bootstrap paths of the backtest's trade R, primary cost model; m-17 the config encodes every promised sensitivity.
