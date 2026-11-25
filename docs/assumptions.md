# H001 build: assumptions and interpretations

The blueprint (v0.2) fixes the rule *options*. Turning them into code needed choices the
blueprint does not spell out. Each one below is a guess about collins's intent and changes
results. Anything marked **config** can be changed in `config/h001.yaml` without code changes;
the rest are code-level readings that need sign-off (Phase 2 gate: "rules signed off by
collins, 20 hand-checked trades match the code"). `grid` writes
`results/audit_sample_20_trades.csv` for that hand check.

## Data and time

1. **Signals use the bid.** Swings, zones, levels, sweeps and confirmations are computed on bid
   prices, as MT5 charts show them. Longs fill at the ask and exit on the bid; shorts fill at
   the bid and exit on the ask.
2. **H4 candles start at the day boundary** (17:00, 21:00, 01:00, 05:00, 09:00, 13:00 New York).
   **config** `calendar.h4_anchor` (`day_boundary` or `utc`). Exness MT5 charts use server time
   (UTC+0 as far as I know, unverified), so their H4 candles differ from these.
3. **Higher-timeframe availability.** A D, W or MN candle is usable from the open of the next
   candle of that timeframe. That is never earlier than its true close, so there is no
   look-ahead; it can be a weekend late, which does not matter because nothing trades then.
4. **Asian session** runs 17:00 New York to 08:00 London (from the config). The "Asian session
   low" is that session's low for the current trading day, usable only after the session ends.
5. **Dukascopy minutes with zero volume are dropped** (they are filler bars).

## Rules

6. **Impulse start.** The candle right after the base must be bullish (bearish for supply).
   The impulse must close at least `impulse_atr_h4` x ATR(H4, at the last base candle) above
   the zone top within `impulse_window_h4_bars`, and above the latest H4 swing high confirmed
   before that candle. A close below the zone bottom during the impulse window cancels it.
7. **nearest_3** looks back at most `nearest_3_max_lookback_h4_bars` (10) from the last base
   candle. **config**. This limit was not in the blueprint.
8. **Touches.** A touch is an H1 bar whose low reaches the zone top after an H1 bar that did not.
   The time limit runs from the first touch only. The zone dies at the start of touch
   number `zone_max_touches + 1`.
9. **Liquidity must be unswept.** For every level type, a level that price already traded
   below before the sweep candle is no longer liquidity and is ignored.
   - `h1_swing`: the most recent confirmed, unswept H1 swing low at the sweep candle's open.
     *This differs from the blueprint text* ("last confirmed H1 swing low before price
     reached the zone"): price usually breaks that low on the way into the zone, so it would
     almost never be a sweepable level. Please confirm.
   - `prev_day`: previous trading day's low, unless already broken earlier in the current day.
   - `asian_session`: see 4; unless already broken after the session ended.
   - `equal_levels`: the most recent two unswept confirmed H1 swing lows, within the last
     `equal_levels_lookback_h1_bars`, that are within `equal_levels_tol_atr_h1` x ATR(H1);
     L is the lower one.
10. **Sweep.** An H1 low below L, then an H1 close above L on the same candle or within
    `close_back_max_h1_bars`. The sweep low may be at most `sweep_max_above_zone_atr_h4` x ATR(H4)
    above the zone top. No close below the zone bottom in between.
11. **Confirmation.** On the execution timeframe, the most recent swing high confirmed before
    the current candle and formed after the sweep low. A close above it confirms. Price
    trading below the sweep low first cancels that sweep; the scanner then keeps looking for a
    new sweep inside the same time window.
12. **One trade per zone.** If the entry candle falls outside the allowed session, after the
    Friday cutoff or inside a news blackout, that entry is skipped and the scanner keeps
    looking for another sweep in the window. A setup with neutral monthly or weekly structure
    at entry time is NO TRADE and uses up the zone.
13. **Setup type is decided at the entry time**, from the last closed MN and W candles.
14. **Confirmation-swing stop** = the lowest low between the broken swing high and the
    confirmation candle (the higher low before the break).
15. **Stop buffer** = `stop_buffer_atr_h1` x ATR(H1) + the spread at entry, for both stop types.
16. **Extended exit.** Target = near edge of the nearest active opposing H4 zone beyond entry,
    capped at `extended_target_cap_r`. If no such zone is at least `target_r` away, the target
    falls back to `target_r`.
17. **Trailing.** After +`trail_start_r`, the stop moves to +`trail_lock_r`, then up to each new
    execution-timeframe swing low (minus the same buffer) confirmed after that point.
    **Partial:** `partial_fraction` closes at +`trail_start_r`, the stop goes to break-even,
    the rest trails the same way. The new stop is checked from the next minute.
18. **Intraday exit** at the open of the last M5 candle before 17:00 New York (16:55 New York),
    on the trading day of entry. An intraday entry at or after 16:55 is skipped.
19. **One open trade per pair** is applied within each strategy and configuration, across both
    directions.

## Costs

20. **Exness Standard has no commission** (dailyforex.com, read 25 Nov 2026: "commission-free
    Standard account ... average EUR/USD spread of 1.0 pips"). Spread used =
    max(Dukascopy spread, floor). Floors: EURUSD 1.0 (that source), GBPUSD 1.3 and USDJPY 1.2
    (**unverified guesses**). Replace with Exness tick files.
21. **Slippage** 0.2 pip per side on entry, stop and time exits; none on targets.
22. **Swap is not modelled** (0) until the Exness swap table is entered in the config. This
    flatters swing trades held for days.
23. **News blackout is off** unless a calendar CSV is passed. The blueprint's free-data plan
    has no consensus feed; a release-time calendar is enough for this filter.

## Statistics

24. Romano-Wolf, PBO and deflated Sharpe use **weekly summed R per configuration** (by exit
    week), because configurations trade on different days and need a common time axis.
25. Walk-forward selection pools the three pairs within a strategy, picks the highest
    expectancy with at least `min_train_trades` training trades, and drops training trades that
    exit after the test year starts.
26. The deflated Sharpe trial count is the larger of the grid size (768) and the trial ledger
    total, so every rerun with new code or settings raises the bar.
