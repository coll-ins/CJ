# Exness MT5 server-time check (to be done by collins on the demo terminal)

H002 research time is UTC. Exness server time is NOT assumed to be UTC. Until this check is
filled in, any comparison between Exness charts and research levels is unverified.

Steps (MT5 desktop, Exness Standard demo):

1. Market Watch: note the server time shown at the top, and the real UTC time at that moment
   (for example from time.is/UTC). Record the offset.
2. Repeat once after the next US and EU DST change (March / late October) to see whether the
   offset moves.
3. Open EURUSD W1: note the open time of the current weekly candle (Sunday or Monday?).
4. Open EURUSD D1: note whether there is a short Sunday daily candle.
5. Open BTCUSD W1 and D1: same notes.

| Date checked | Server time | UTC | Offset | W1 candle opens | Sunday D1 candle? | By |
|---|---|---|---|---|---|---|
| | | | | | | |

If the offset is not 0 or the W1 candle opens on Sunday, Exness weekly highs/lows will differ
from H002's Monday-00:00-UTC levels. The forward-demo logger then computes levels from UTC
timestamps itself rather than reading MT5's W1 bars.
