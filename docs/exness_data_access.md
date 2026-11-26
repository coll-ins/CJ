# Exness data access: what can be retrieved programmatically (checked 2026-11-26)

Labels: [E] verified by an actual request from this environment, [U] unverified / from
third-party text only.

## 1. Historical tick archive (bid/ask) — AVAILABLE [E]

* Host: `ticks.ex2archive.com` (the file server behind Exness's public Tick History page).
  Added to the CJ cloud environment's allowed hosts on 26 Nov (collins approved).
  `ticks.exness.com` is allowed too but did not resolve (proxy 502).
* No authentication. Directory listings are JSON: `/ticks/` lists 1,522 symbol folders;
  `/ticks/{SYMBOL}/{YYYY}/{MM}/Exness_{SYMBOL}_{YYYY}_{MM}.zip` holds one CSV per month,
  plus a yearly zip for the current year.
* CSV columns: `"Exness","Symbol","Timestamp","Bid","Ask"`; timestamp is UTC with
  millisecond precision (`2026-10-01 00:00:02.251Z`). Real bid AND ask on every tick.
* Account-type variants per symbol: suffix `m`, `c`, none, `_Raw_Spread`, `_Zero_Spread`,
  `_Standart_Plus`. EURUSD October 2026, median tick spread: `m` 0.8 pip, `c` 0.8, none 0.6,
  `_Standart_Plus` 1.1, `_Raw_Spread` 0.0, `_Zero_Spread` 0.0 pip.
  **Inference [U]: `m` = Standard** (Standard and Standard Cent share spreads; plain = Pro).
  To be confirmed by the symbol name collins sees on the demo account.

Coverage of the Standard (`m`) series for our six instruments [E]:

| Instrument | Exness symbol | First month | Last month | Missing vs H002 2011 start |
|---|---|---|---|---|
| EURUSD | EURUSDm | 2015-08 | 2026-11 (in progress) | 2011-01 to 2015-07 |
| GBPUSD | GBPUSDm | 2015-08 | 2026-11 | 2011-01 to 2015-07 |
| USDJPY | USDJPYm | 2015-08 | 2026-11 | 2011-01 to 2015-07 |
| XAUUSD | XAUUSDm | 2015-08 | 2026-11 | 2011-01 to 2015-07 |
| BTCUSD | BTCUSDm | 2017-09 | 2026-11 | 2017-08 (2 weeks) |
| NAS100 | USTECm | 2019-08 | 2026-11 | 2011-01 to 2019-07 |

Sizes: 7 MB (EURUSD month, 2026) to 25 MB (BTC month, 2018) zipped; roughly 10 to 15 GB for
all six instruments over full coverage.

Spot checks (median of ticks, not time-weighted) [E]:
* EURUSDm Oct 2026: 0.8 pip (p10 and p90 also 0.8). H001/H002 fallback floor was 1.0.
* BTCUSDm Jun 2018: $13.91 = 20.2 bp at ~$7,500 (p10 $7.10, p90 $32.49). Neither the old flat
  $20 nor the withdrawn 2 bp matches.
* XAUUSD screenshot 25 Nov 2026: $0.221 = 0.62 bp (one tick, not from the archive).

This is a real historical spread record for 2015/2017/2019 onward, much better than the
3-month MT5 export planned in v0.4 step B. It does not cover 2011 to mid-2015 (FX, gold) or
2011 to mid-2019 (NAS100).

## 2. Historical candles — not needed from Exness
Candles do not carry the spread path; H002 does not use them for costs. HistData/Binance M1
stay the signal data as approved.

## 3. Live tick streaming — not needed before the forward demo
Options: MT5 terminal with the `MetaTrader5` Python package (`symbol_info_tick`,
`copy_ticks_from`), Windows only and needs a logged-in terminal [U]; or the Exness API [U].

## 4. Instrument specification, swap and swap-free — NOT available programmatically from here
* The tick archive has no spread settings, swap or contract fields [E].
* `MetaTrader5` Python package: `symbol_info(symbol)` returns `spread`, `swap_long`,
  `swap_short`, `swap_mode`, `swap_rollover3days`, `trade_contract_size`, `digits` [U: from
  MQL5 docs, not run here]. Needs Windows + MT5 terminal logged in to the demo account; gives
  current values only, no history.
* Exness API: Exness's help centre says keys are created in the Personal Area for eligible,
  verified trading accounts [U: help-centre snippet; exness.com is unreachable from this
  environment, so eligibility of a demo account is unconfirmed].
* Swap-free status is an account property in the Personal Area. No public endpoint found [U].
* **Historical swap rates: no source found anywhere.** S3 can only ever be "current rates
  applied to history".

## 5. Server time
The archive's timestamps are UTC ("Z"), so H002 cost data does not depend on the MT5 server
offset. The forward demo still needs the offset: either a manual check, or `MetaTrader5`
`symbol_info_tick().time` vs UTC on a Windows machine [U].
