import sys, time, pandas as pd
from pathlib import Path
from cjfx.config import load_config
from cjfx.cli import load_bars
from cjfx.diagnostics import run_components, mfe_table, target_expectancy
from cjfx.market import Market
cfg=load_config(); out=Path('results/diagnostics'); out.mkdir(parents=True,exist_ok=True)
tr=pd.read_parquet('results/trades.parquet')
comp=[]; mfes=[]
for p in sys.argv[1:]:
    t=time.time(); bars,_,_=load_bars(Path('data'),p,cfg)
    df=run_components(p,bars,cfg); comp.append(df); print(p,'components',round(time.time()-t),flush=True)
    u=tr[(tr.pair==p)&(tr.stop=='sweep_wick')&(tr.exit=='fixed_3r')].drop_duplicates(['direction','execution','entry_time','impulse_atr'])
    mk={d:Market(p,bars,cfg,d) for d in (1,-1)}
    mfes.append(mfe_table(u,mk,cfg)); print(p,'mfe',len(mfes[-1]),flush=True)
pd.concat(comp).to_csv(out/'components.csv',index=False)
pd.concat(mfes).to_parquet(out/'mfe.parquet')
