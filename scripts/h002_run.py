"""H002 run for the given instruments into results/h002/final (spec v0.6, frozen config)."""
import sys
import time
from pathlib import Path

from cjfx.h002.run import load_cfg, run_instrument

out = Path(__file__).parents[1] / "results/h002/final"
t0 = time.time()
for name in sys.argv[1:]:
    run_instrument(name, load_cfg(), out, log=lambda s: print(f"{time.time() - t0:8.0f}s {s}", flush=True))
