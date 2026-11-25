"""Build H002 spread cost inputs from the Exness public tick archive (costs only)."""
import sys
from pathlib import Path

import yaml

from cjfx.h002.spread_archive import build

cfg = yaml.safe_load(open(Path(__file__).parents[1] / "config/h002.yaml"))
series = list(cfg["costs"]["spread"]["series"].values())
if len(sys.argv) > 1:
    series = sys.argv[1:]
build(series, Path(__file__).parents[1] / "results/h002", log=lambda s: print(s, flush=True))
