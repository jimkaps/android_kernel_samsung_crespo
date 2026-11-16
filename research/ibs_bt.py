"""IBS mean-reversion backtests on NQ (daily). IBS = (C-L)/(H-L).
Entries/exits at the close (assumes you act just before the close using near-close IBS).
Returns in % of price; cost per round trip deducted (default 1.5 NQ points ~ slippage+fees)."""
import sys, numpy as np, pandas as pd

def load(f):
    d = pd.read_csv(f, index_col=0, parse_dates=True)[['Open','High','Low','Close']].dropna()
    d = d[d.High > d.Low]
    if d.index[-1] >= pd.Timestamp('2026-11-16'): d = d.iloc[:-1]   # drop today's partial bar
    d['ibs'] = (d.Close - d.Low) / (d.High - d.Low)
    d['ret'] = d.Close.pct_change().shift(-1)        # next close-to-close return
    return d

def run(d, entry, exit_rule, side=1, cost_pts=1.5, max_hold=10):
    C, H, ibs = d.Close.values, d.High.values, d.ibs.values
    trades = []; i = 0; n = len(d)
    while i < n - 1:
        if entry(d, i):
            j = i + 1
            while j < n - 1 and not exit_rule(d, i, j) and j - i < max_hold: j += 1
            r = side * (C[j] / C[i] - 1) - cost_pts / C[i]
            trades.append((d.index[i], d.index[j], r, j - i)); i = j
        else: i += 1
    return pd.DataFrame(trades, columns=['entry','exit','r','bars'])

def stats(t, label):
    if len(t) == 0: return print(f'{label:52s} no trades')
    r = t.r; yrs = (t.entry.iloc[-1] - t.entry.iloc[0]).days / 365.25
    eq = (1 + r).cumprod(); dd = (eq / eq.cummax() - 1).min()
    ts = r.mean() / r.std() * np.sqrt(len(r))
    def sub(a, b):
        s = r[(t.entry >= a) & (t.entry < b)]; return f'{s.mean()*100:+.3f}%/t{s.mean()/s.std()*np.sqrt(len(s)):+.1f}' if len(s) > 5 else '   -   '
    print(f'{label:52s} n={len(r):4d} win={(r>0).mean():.0%} avg={r.mean()*100:+.3f}% t={ts:+.2f} '
          f'CAGR={(eq.iloc[-1]**(1/yrs)-1)*100:+5.1f}% DD={dd*100:5.1f}% inmkt={t.bars.sum()/(yrs*252):.0%} | '
          f'00-09 {sub("2000","2010")}  10-17 {sub("2010","2018")}  18-26 {sub("2018","2027")}')

if __name__ == '__main__':
    d = load(sys.argv[1]); lo, hi = 0.2, 0.8
    up_exit  = lambda d, i, j: d.Close.iat[j] > d.High.iat[j-1]           # close above prior high
    ibs_exit = lambda d, i, j: d.ibs.iat[j] > hi
    nxt      = lambda d, i, j: True
    print(f'== {sys.argv[1]}  {d.index[0].date()} .. {d.index[-1].date()}')
    print('-- baseline: buy & hold every day'); stats(pd.DataFrame({'entry':d.index[:-1],'r':d.ret[:-1],'bars':1}), 'B&H daily close-to-close')
    for x in (0.1, 0.2, 0.3):
        stats(run(d, lambda d,i,x=x: d.ibs.iat[i] < x, nxt), f'1) IBS<{x} long, exit next close')
    stats(run(d, lambda d,i: d.ibs.iat[i] < lo, up_exit), '2) IBS<0.2 long, exit close>prev high')
    stats(run(d, lambda d,i: d.ibs.iat[i] < lo, ibs_exit), '3) IBS<0.2 long, exit IBS>0.8')
    # "double IBS": two consecutive low-IBS days
    dbl = lambda x: (lambda d,i: i > 0 and d.ibs.iat[i] < x and d.ibs.iat[i-1] < x)
    for x in (0.2, 0.3, 0.4):
        stats(run(d, dbl(x), nxt), f'4) DOUBLE IBS<{x} (2 days) long, exit next close')
        stats(run(d, dbl(x), up_exit), f'5) DOUBLE IBS<{x} (2 days) long, exit close>prev high')
    # avg of two days' IBS
    stats(run(d, lambda d,i: i>0 and (d.ibs.iat[i]+d.ibs.iat[i-1])/2 < 0.25, nxt), '6) 2-day avg IBS<0.25 long, exit next close')
    # IBS low + below 200d/above 200d filter
    ma = d.Close.rolling(200).mean().values
    stats(run(d, lambda d,i: d.ibs.iat[i] < lo and d.Close.iat[i] > ma[i], nxt), '7) IBS<0.2 & above 200d MA, exit next close')
    stats(run(d, lambda d,i: i>0 and d.ibs.iat[i] < 0.3 and d.ibs.iat[i-1] < 0.3 and d.Close.iat[i] > ma[i], up_exit), '8) DOUBLE IBS<0.3 & >200d MA, exit close>prev high')
    # short side (double-sided IBS)
    stats(run(d, lambda d,i: d.ibs.iat[i] > 0.9, nxt, side=-1), '9) SHORT IBS>0.9, exit next close')
    stats(run(d, lambda d,i: i>0 and d.ibs.iat[i] > 0.8 and d.ibs.iat[i-1] > 0.8, nxt, side=-1), '10) SHORT DOUBLE IBS>0.8, exit next close')
