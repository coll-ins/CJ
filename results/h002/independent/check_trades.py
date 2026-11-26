"""Independent hand-check of 20 H002 trades against M1 bars (spec 3.3, 3.4, B-1, B-4, M-7/8/9)."""
import numpy as np
import pandas as pd

D = '/tmp/claude-0/-home-user/6120cbf8-4f0e-501c-87a5-4780383bf2e9/scratchpad/indep/'
SLIP = 0.2e-4
prof = pd.read_csv('/home/user/CJ/results/h002/spread_profiles.csv')
ci = pd.read_csv('/home/user/CJ/results/h002/cost_inputs.csv')
m1 = {s: pd.read_parquet(f'/home/user/CJ/data/m1/{s}_M1.parquet', columns=['bid_o', 'bid_h', 'bid_l', 'bid_c'])
      for s in ['EURUSD', 'GBPUSD']}

bucket = {(r.series, r.month, int(r.how)): r.median for r in prof.itertuples()}
monthmed = {(r.series, r.month): r.median_spread for r in ci.itertuples()}
first_month = {s: sorted(m for (ss, m) in monthmed if ss == s)[0] for s in ['EURUSDm', 'GBPUSDm']}
pre = {}
for s, fm in first_month.items():
    months = [str(p) for p in pd.period_range(fm, periods=12, freq='M')]
    sub = prof[(prof.series == s) & prof.month.isin(months)]
    pre[s] = sub.groupby('how')['median'].median().to_dict()
    pre[s, 'all'] = float(np.median([monthmed[(s, m)] for m in months]))


def spread(sym, t):
    s = sym + 'm'
    how = t.weekday() * 24 + t.hour
    pm = str((t.tz_convert(None).to_period('M') - 1))
    if pm < first_month[s]:
        return pre[s].get(how, pre[s, 'all'])
    return bucket.get((s, pm, how), monthmed[(s, pm)])


rows = []
def wilder(b):
    h,l,c=b.bid_h.values,b.bid_l.values,b.bid_c.values
    pc=np.r_[np.nan,c[:-1]]
    trr=np.where(np.isnan(pc),h-l,np.maximum(h,pc)-np.minimum(l,pc))
    a=np.full(len(trr),np.nan); a[13]=trr[:14].mean()
    for q in range(14,len(trr)): a[q]=(a[q-1]*13+trr[q])/14
    return pd.Series(a,index=b.index)
ATR={}
for sym in m1:
    for tf,f in [('M5','5min'),('M15','15min'),('H1','1h')]:
        bb=m1[sym].resample(f,label='left',closed='left').agg({'bid_o':'first','bid_h':'max','bid_l':'min','bid_c':'last'}).dropna()
        ATR[sym,tf]=wilder(bb)
tr = pd.read_csv(D + 'trades20.csv')
for x in tr.itertuples():
    b = m1[x.instrument]
    long = x.side == 'low'
    rc = pd.Timestamp(x.reclaim_close_t)
    tfd = {'M5': 5, 'M15': 15, 'H1': 60}[x.tf]
    rc_open = rc - pd.Timedelta(minutes=tfd)
    # entry: first existing M1 bar at/after reclaim close (open of next M5 bar)
    k = b.index.searchsorted(rc)
    te = b.index[k]
    o = b.bid_o.iloc[k]
    se = spread(x.instrument, te)
    entry = o + se + SLIP if long else o - SLIP
    sstop = spread(x.instrument, rc_open)          # I-2: reclaim candle's hour
    myatr = ATR[x.instrument, x.tf].loc[rc_open]
    buf = 0.1 * myatr
    stop = x.extreme - buf - sstop if long else x.extreme + buf + sstop
    R = abs(entry - stop)
    tgt = entry + 3 * R if long else entry - 3 * R
    # weekly flat: Fri 20:00 UTC of entry week
    fri = (te.normalize() - pd.Timedelta(days=te.weekday()) + pd.Timedelta(days=4, hours=20))
    if te >= fri:
        fri += pd.Timedelta(days=7)
    out = None
    j = k
    while True:
        t = b.index[j]
        if t >= fri:
            sp = spread(x.instrument, t)
            ex = b.bid_o.iloc[j] - SLIP if long else b.bid_o.iloc[j] + sp + SLIP
            out = ('weekly_flat', t, ex)
            break
        sp = spread(x.instrument, t)
        bo, bh, bl = b.bid_o.iloc[j], b.bid_h.iloc[j], b.bid_l.iloc[j]
        if long:
            if bl <= stop:
                ex = (bo if bo <= stop and j > k else stop) - SLIP
                out = ('stop', t, ex); break
            if bh >= tgt:
                out = ('target', t, tgt); break
        else:
            if bh + sp >= stop:
                ex = (bo + sp if bo + sp >= stop and j > k else stop) + SLIP
                out = ('stop', t, ex); break
            if bl + sp <= tgt:
                out = ('target', t, tgt); break
        j += 1
    oc, tx, ex = out
    r = (ex - entry) / R if long else (entry - ex) / R
    mine = dict(atr=myatr, t_entry=te, entry=entry, stop=stop, target=tgt, R=R, outcome=oc, t_exit=tx, exit=ex, r=r)
    diffs = []
    for f, v in mine.items():
        g = getattr(x, f)
        if f in ('t_entry', 't_exit'):
            ok = pd.Timestamp(g) == v
        elif f == 'outcome':
            ok = g == v
        else:
            ok = abs(float(g) - v) < (1e-4 if f == 'r' else 1e-8)
        if not ok:
            diffs.append(f'{f}: given {g} mine {v}')
    row = dict(i=x.Index, instrument=x.instrument, source=x.source, tf=x.tf, side=x.side,
               **{f'my_{f}': v for f, v in mine.items()},
               given_outcome=x.outcome, given_r=x.r, match='match' if not diffs else 'mismatch',
               detail='; '.join(diffs))
    rows.append(row)

df = pd.DataFrame(rows)
df.to_csv(D + 'trades20_check.csv', index=False)
print(df[['i', 'instrument', 'tf', 'side', 'my_outcome', 'given_outcome', 'my_r', 'given_r', 'match']].to_string())
for d in df[df.match != 'match'].itertuples():
    print(d.i, d.detail)
