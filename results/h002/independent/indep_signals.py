"""Independent re-implementation of the H002 sweep/reclaim signal state machine (spec v0.6).
Written from docs/h002_spec.md + config/h002.yaml only. EURUSD, sweeps opening in 2019."""
import numpy as np
import pandas as pd

DATA = '/home/user/CJ/data/m1/EURUSD_M1.parquet'
OUT = '/tmp/claude-0/-home-user/6120cbf8-4f0e-501c-87a5-4780383bf2e9/scratchpad/indep/'
PT = 1e-5                       # EURUSD quoted to 5 dp; work in integer points
PMIN = 10                       # 1.0 pip = 10 points
WIN = pd.Timedelta(minutes=60)
TFS = {'M5': '5min', 'M15': '15min', 'H1': '1h'}
Y0, Y1 = pd.Timestamp('2019-01-01', tz='UTC'), pd.Timestamp('2020-01-01', tz='UTC')

m1 = pd.read_parquet(DATA, columns=['bid_o', 'bid_h', 'bid_l', 'bid_c'])
m1.columns = ['o', 'h', 'l', 'c']
m1 = (m1 * 1e5).round().astype(np.int64)


def resample(freq):
    b = m1.resample(freq, label='left', closed='left').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'})
    return b.dropna().astype(np.int64)          # only bars that have data


def wilder_atr(b):
    """M-5: Wilder ATR14, seed = mean of first 14 TRs, existing bars only, prev existing close.
    First bar of the series has no previous close: TR = high - low."""
    h, l, c = b.h.values.astype(float), b.l.values.astype(float), b.c.values.astype(float)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.where(np.isnan(pc), h - l, np.maximum(h, pc) - np.minimum(l, pc))
    tr[0] = h[0] - l[0]
    atr = np.full(len(tr), np.nan)
    atr[13] = tr[:14].mean()
    for k in range(14, len(tr)):
        atr[k] = (atr[k - 1] * 13 + tr[k]) / 14
    return atr                                   # atr[k] = ATR through bar k (in points)


bars = {tf: resample(f) for tf, f in TFS.items()}
atrs = {tf: wilder_atr(b) for tf, b in bars.items()}

# ---------------------------------------------------------------- weekend window (B-1)
def in_weekend_window(t):
    """Fri 20:00 UTC .. Mon 00:00 UTC (Sat/Sun entirely)."""
    wd = t.weekday()
    return (wd == 4 and t.hour >= 20) or wd in (5, 6)

# ---------------------------------------------------------------- PW levels
wk = m1.index.tz_convert(None).to_period('W-SUN')   # weeks Mon..Sun
wkhl = m1.groupby(wk).agg(h=('h', 'max'), l=('l', 'min'))
levels = []   # dict(source, side, segs=[(t_from, price)], avail, expiry)
for p in wkhl.index:
    start = pd.Timestamp(p.end_time.normalize(), tz='UTC') + pd.Timedelta(days=1)   # next Monday 00:00
    if start < Y0 - pd.Timedelta(days=14) or start > Y1 + pd.Timedelta(days=7):
        continue
    exp = start + pd.Timedelta(days=7)
    levels.append(dict(source='pw', side='high', segs=[(start, int(wkhl.loc[p, 'h']))], avail=start, expiry=exp))
    levels.append(dict(source='pw', side='low', segs=[(start, int(wkhl.loc[p, 'l']))], avail=start, expiry=exp))

# ---------------------------------------------------------------- EQ clusters (2.2 + B-3)
H1 = bars['H1'].loc['2018-10-01':'2020-01-15']
h1_atr = pd.Series(atrs['H1'], index=bars['H1'].index).loc[H1.index].values
H1t = H1.index


def tday(t):
    """B-3(e): trading-day ordinal on UTC dates Mon-Fri; Sunday (and Saturday) counts as next Monday."""
    d = t.tz_convert(None).normalize()
    wd = d.weekday()
    if wd == 5:
        d += pd.Timedelta(days=2)
    elif wd == 6:
        d += pd.Timedelta(days=1)
    return int(np.busday_count(np.datetime64('2000-01-03'), np.datetime64(d.date())))


def tday_date(n):
    return pd.Timestamp(np.busday_offset(np.datetime64('2000-01-03'), n, roll='forward'), tz='UTC')


def build_eq(side):
    sgn = 1 if side == 'high' else -1
    x = (H1.h.values if side == 'high' else -H1.l.values).astype(np.int64)  # mirror lows to highs
    n = len(x)
    singles = []    # dict(bar, price, td)
    clusters = []   # dict(members=[...], level, avail, alive, expiry, segs)
    out = []
    for j in range(n):
        t_open = H1t[j]
        # 1) sweeps / expiry of alive clusters by this bar (formation-level, TF independent)
        for cl in clusters:
            if not cl['alive']:
                continue
            if t_open >= cl['expiry']:
                cl['alive'] = False
            elif t_open >= cl['avail'] and x[j] >= cl['level'] + PMIN:
                cl['alive'] = False
        # 2) pivot confirmation at close of bar j = i+3
        i = j - 3
        if i < 3:
            continue
        if not (x[i] > x[i - 3:i].max() and x[i] > x[i + 1:i + 4].max()):
            continue
        P = int(x[i]); td = tday(H1t[i]); tol = 0.10 * h1_atr[j]; conf_t = H1t[j] + pd.Timedelta(hours=1)
        cands = []
        for cl in clusters:
            if not cl['alive']:
                continue
            if abs(P - cl['level']) > tol + 1e-9:
                continue
            if P >= cl['level'] + PMIN:       # B-3(c): sweep, never member
                continue
            if td - min(m['td'] for m in cl['members']) > 5:
                continue
            lvl = max(cl['level'], P)
            ob = min(m['bar'] for m in cl['members'])
            if i - ob > 1 and x[ob + 1:i].max() >= lvl + PMIN:
                continue
            cands.append((max(m['bar'] for m in cl['members']), 'c', cl))
        for q in singles:
            if abs(P - q['price']) > tol + 1e-9:
                continue
            if td - q['td'] > 5:
                continue
            lvl = max(q['price'], P)
            if i - q['bar'] > 1 and x[q['bar'] + 1:i].max() >= lvl + PMIN:
                continue
            cands.append((q['bar'], 's', q))
        me = dict(bar=i, price=P, td=td)
        if not cands:
            singles.append(me)
            continue
        cands.sort(key=lambda z: z[0])
        _, kind, obj = cands[-1]                  # A-5: most recent
        if kind == 'c':
            obj['members'].append(me)
            if P > obj['level']:
                obj['level'] = P
                obj['segs'].append((conf_t, P))
            obj['expiry'] = exp_from(td)
            obj['ntouch'].append((conf_t, len(obj['members'])))
        else:
            singles.remove(obj)
            lvl = max(obj['price'], P)
            cl = dict(members=[obj, me], level=lvl, avail=conf_t, alive=True,
                      expiry=exp_from(td), segs=[(conf_t, lvl)], ntouch=[(conf_t, 2)], expiries=[])
            clusters.append(cl)
            out.append(cl)
        # record expiry history (expiry can only extend)
        tgt = obj if kind == 'c' else cl
        tgt.setdefault('expiries', []).append((conf_t, tgt['expiry']))
    res = []
    for cl in out:
        res.append(dict(source='eq', side=side,
                        segs=[(t, sgn * p) for t, p in cl['segs']],
                        avail=cl['avail'], expiries=cl['expiries'], expiry=cl['expiry'],
                        n=len(cl['members'])))
    return res


def exp_from(td_newest):
    """Expiry at 00:00 UTC after the 5th trading day following the newest pivot's trading day."""
    return tday_date(td_newest + 5) + pd.Timedelta(days=1)


eq_levels = build_eq('high') + build_eq('low')
levels += eq_levels

# ---------------------------------------------------------------- state machine (3.2 + v0.6)
def expiry_at(lv, t):
    if 'expiries' not in lv:
        return lv['expiry']
    e = None
    for tc, ex in lv['expiries']:
        if tc <= t:
            e = ex
    return e


def price_at(lv, t):
    p = None
    for tf_, pr in lv['segs']:
        if tf_ <= t:
            p = pr
    return p


rows, allrows = [], []
for tf, b in bars.items():
    dur = pd.Timedelta(TFS[tf])
    bt = b.index
    H, L, C = b.h.values, b.l.values, b.c.values
    atr = atrs[tf]
    for lv in levels:
        k = bt.searchsorted(lv['avail'])          # m-2: first candle opening at/after availability
        swept = False
        while k < len(bt):
            t = bt[k]
            if not swept:
                if t >= expiry_at(lv, t):
                    break                                       # expired unswept
                Lp = price_at(lv, t)
                hit = H[k] >= Lp + PMIN if lv['side'] == 'high' else L[k] <= Lp - PMIN
                if not hit:
                    k += 1
                    continue
                swept, sk, L0 = True, k, Lp
                deadline = t + WIN
                ext = H[k] if lv['side'] == 'high' else L[k]
            else:
                ext = max(ext, H[k]) if lv['side'] == 'high' else min(ext, L[k])
            ct = t + dur
            a = atr[k - 1]
            if lv['side'] == 'high':
                rec, cons = C[k] < L0, C[k] > L0 + a
            else:
                rec, cons = C[k] > L0, C[k] < L0 - a
            if rec and ct <= deadline:
                st = 'reclaim'
            elif cons:
                st = 'consumed'
            elif ct >= deadline:
                st = 'expired'
            else:
                k += 1
                continue
            sw_t = bt[sk]
            wknd = in_weekend_window(sw_t) or (st == 'reclaim' and in_weekend_window(ct))
            r = dict(source=lv['source'], side=lv['side'], tf=tf, level=round(L0 * PT, 5),
                     sweep_t=sw_t.isoformat(), reclaim_close_t=ct.isoformat() if st == 'reclaim' else '',
                     extreme=round(ext * PT, 5), status=st if not (wknd and st == 'reclaim') else 'weekend_window')
            if Y0 <= sw_t < Y1:
                allrows.append(r)
                if st == 'reclaim' and not wknd:
                    rows.append(r)
            break

cols = ['source', 'side', 'tf', 'level', 'sweep_t', 'reclaim_close_t', 'extreme', 'status']
df = pd.DataFrame(rows, columns=cols).sort_values(['source', 'tf', 'sweep_t', 'side', 'level'])
df.to_csv(OUT + 'signals_EURUSD_2019.csv', index=False)
pd.DataFrame(allrows, columns=cols).sort_values(['source', 'tf', 'sweep_t']).to_csv(OUT + 'all_outcomes_EURUSD_2019.csv', index=False)
print(df.groupby(['source', 'tf']).size())
print(pd.DataFrame(allrows).groupby(['source', 'tf', 'status']).size())
