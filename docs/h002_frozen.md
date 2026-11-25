# H002 freeze record

Frozen by collins on 2026-11-25 22:58 UTC (26 Nov 01:58 Nairobi), message: "freeze".
Frozen content = commit `9cf9556` (spec v0.5). Any rule change after this is a new version
(v0.6+) that needs collins's approval and restarts any forward record.

SHA-256 of the frozen files as they are in commit 9cf9556:

```
7d5c85ee2c00bfdbc5c16d56b17e5e98a3f90ad67fea42f7a724a5396c8ac08e  docs/h002_spec.md
1cb8112c47de7376441fe1cfddbafcf382b0921ac49621fb598b73e995a80a54  config/h002.yaml
```

The commit that records this freeze only changes status lines (status, frozen_at, version
table), not rules.

Inputs the frozen spec says are filled in before the first run (data, not rule changes):
1. Confirmation of the Standard symbol suffix (`m` inferred). PENDING collins.
2. Spread-unit regression output for the extrapolated period, from the archive.
3. `results/h002/cost_inputs.csv` with archive file hashes.

Known gap at freeze: spec section 4.9 calls for an independent agent review **before** the
freeze. It had not run when collins froze. It runs next, before any engine code; any finding
that needs a rule change goes to collins as v0.6, never silently.

Not needed for the historical run: swap screenshots (S3 optional), server-time check (forward
demo only).
