# Exness demo terminal evidence (collins fills this in)

H002 does not assume anything about Exness's clock, spreads or swaps. Each item below stays
**PENDING** until collins supplies the evidence (screenshot or exported file).

## Observations received

| Date (UTC) | What | Value | Source | Notes |
|---|---|---|---|---|
| 2026-11-25 21:08 | XAUUSD bid/ask | 3575.057 / 3575.278, spread $0.221 (0.62 bp) | collins's screenshot, Exness Terminal app, M5 chart | one tick, late NY session; the chart's "UTC+3" is the app's display setting, NOT server time |

## A. Server time — PENDING

The screenshot above does not settle it: the app shows times in a user-chosen zone.
On **MT5** (desktop or mobile):

1. Market Watch: note the server time at the top, and real UTC at the same moment
   (e.g. time.is/UTC). Record the offset.
2. Repeat after the next DST change (March) to see whether the offset moves.
3. EURUSD W1: open time of the current weekly candle (Sunday or Monday?).
4. EURUSD D1: is there a short Sunday daily candle?
5. BTCUSD W1 and D1: same notes.

| Date checked | Server time | UTC | Offset | W1 opens | Sunday D1? |
|---|---|---|---|---|---|
| | | | | | |

If the offset is not 0 or W1 opens on Sunday, the forward-demo logger computes levels from UTC
timestamps itself and never reads MT5's W1 bars.

## B. Spread history — LARGELY REPLACED by the public Exness tick archive (see docs/exness_data_access.md)

Still needed from collins: confirm the symbol names on the demo account (EURUSDm style = Standard?).
The MT5 export below is only needed if collins wants a cross-check.

For each of EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD, the NAS100 symbol (Exness: USTEC):
View > Symbols > Ticks tab > choose symbol > date range = last 3 months > Request > Export.
Send the CSV files. They give the broker's real bid and ask, so the spread by hour of week and
whether BTC/gold spreads scale with price come from Exness data instead of guesses.
Also note the exact symbol names and any suffix (e.g. `EURUSDm`), and the account type shown.

## C. Swap — PENDING

For each instrument: Market Watch > right-click > Specification. Screenshot Swap type,
Swap long, Swap short, and the 3-day swap weekday. Record the date (rates change).

| Instrument | Date | Swap type | Long | Short | Triple day |
|---|---|---|---|---|---|
| | | | | | |

## D. Swap-free status — PENDING

Exness Personal Area > Trading conditions: does the account show swap-free / extended
swap-free? Yes or no, with a screenshot.
