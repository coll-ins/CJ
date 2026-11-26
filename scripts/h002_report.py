"""H002 stats + markdown summary over results/h002/final (spec 4.4, 7)."""
from pathlib import Path

import numpy as np
import pandas as pd

from cjfx.h002.run import load_cfg
from cjfx.h002.stats import run_study

ROOT = Path(__file__).parents[1]
res = ROOT / "results/h002/final"
out = ROOT / "results/h002/final/stats"
r = run_study(res, load_cfg(), out)
f = r["family"]


def fmt(v, d=3):
    return "" if v is None or (isinstance(v, float) and not np.isfinite(v)) else (f"{v:.{d}f}" if isinstance(v, float) else str(v))


cols = ["instrument", "source", "tf", "filter", "executed", "expectancy", "t", "p_rw", "pos_years", "long_e", "short_e",
        "E_spread_x1.5", "swap_s1_e", "E_buffer_0.05", "E_buffer_0.2", "beats_placebo", "dsr_54", "exposed_n",
        "exposed_e", "breakeven_spread_mult", "unscorable_share", "pass_all"]
lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
for _, x in f.iterrows():
    lines.append("| " + " | ".join(fmt(x[c]) for c in cols) + " |")
(out / "family_54.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
print("var_sr", f.attrs.get("var_sr"))
print("cells passing all:", int(f.pass_all.sum()), "| c1:", int(f.c1_sig.sum()), "| bonferroni:", int(f.c1_bonf.sum()),
      "| E>0:", int((f.expectancy > 0).sum()), "of", len(f))
