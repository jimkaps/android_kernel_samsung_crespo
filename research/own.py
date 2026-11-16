import numpy as np, pandas as pd
from ibs_bt import load
d = load('NQ_F.csv'); d = d[d.index >= '2000-10-01']
PX = 25000; NOT = 2 * PX; COST = 4 / NOT            # 1 MNQ notional today, $4 round trip
C, H, L, O, ibs = d.Close.values, d.High.values, d.Low.values, d.Open.values, d.ibs.values
def run(thr, exit_rule, stop=None, max_hold=10):
    tr = []; i = 1; n = len(d); daily = np.zeros(n)
    while i < n - 1:
        if ibs[i] < thr and ibs[i-1] < thr:
            e = C[i]; j = i + 1; ex = None
            while True:
                if stop and L[j] <= e * (1 - stop):
                    ex = min(O[j], e * (1 - stop)); break           # gap through -> open
                if exit_rule == 'next' or C[j] > H[j-1] or j - i >= max_hold or j == n - 1:
                    ex = C[j]; break
                j += 1
            r = ex / e - 1 - COST; tr.append((d.index[i], r, j - i))
            prev = e
            for k in range(i + 1, j + 1):                          # mark-to-market daily
                px = ex if k == j else C[k]; daily[k] += (px - prev) / e; prev = px
            daily[j] -= COST; i = j
        else: i += 1
    t = pd.DataFrame(tr, columns=['date', 'r', 'bars']); eq = pd.Series(daily * NOT, d.index).cumsum()
    return t, eq
print(f'1 MNQ, sized at NQ={PX} (notional ${NOT:,.0f}); all history scaled to today\'s price\n')
print('rule                                  trades/yr win   avg$/tr  $/yr   worst trade  worst DD   longest underwater  worst year')
out = {}
for name, thr, ex, st in [('DOUBLE<0.3, exit next close', 0.3, 'next', None),
                          ('DOUBLE<0.3, exit close>prev high', 0.3, 'prevH', None),
                          ('DOUBLE<0.3, exit close>prev high, 3% stop', 0.3, 'prevH', 0.03),
                          ('DOUBLE<0.35, exit next close', 0.35, 'next', None),
                          ('DOUBLE<0.4, exit close>prev high, 3% stop', 0.4, 'prevH', 0.03)]:
    t, eq = run(thr, ex, st); yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    dd = eq - eq.cummax(); uw = (dd < 0).astype(int); grp = (uw.diff() != 0).cumsum(); longest = uw.groupby(grp).sum().max()
    yr = eq.resample('YE').last().diff().fillna(eq.resample('YE').last().iloc[0])
    print(f'{name:40s} {len(t)/yrs:5.0f} {np.mean(t.r>0):4.0%} {t.r.mean()*NOT:+8.0f} {eq.iloc[-1]/yrs:+7.0f} {t.r.min()*NOT:+10.0f} {dd.min():+9.0f}   {longest/252:4.1f} yrs        {yr.min():+.0f} ({yr.idxmin().year})')
    out[name] = (t, eq, yr)
t, eq, yr = out['DOUBLE<0.3, exit close>prev high, 3% stop']
print('\nchosen rule, $ per year (1 MNQ):', yr.round().astype(int).rename(lambda x: x.year).to_dict())
dd = eq - eq.cummax(); print('worst DD from', eq[:dd.idxmin()].idxmax().date(), 'to', dd.idxmin().date())
# also: worst DD in the last 10 yrs
e2 = eq[eq.index >= '2016']; print('worst DD since 2016: %.0f' % (e2 - e2.cummax()).min())
eq.to_csv('own_eq.csv')
