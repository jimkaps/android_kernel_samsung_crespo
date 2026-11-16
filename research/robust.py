import sys, numpy as np, pandas as pd
sys.path.insert(0,'.'); from ibs_bt import load, run
up_exit=lambda d,i,j: d.Close.iat[j]>d.High.iat[j-1]; nxt=lambda d,i,j: True
dbl=lambda x:(lambda d,i: i>0 and d.ibs.iat[i]<x and d.ibs.iat[i-1]<x)
for f,cost in [('NQ_F.csv',1.5),('ES_F.csv',0.5),('QQQ.csv',0.02)]:
    d=load(f); d=d[d.index>='2000-01-01']; bh=d.ret.mean()
    print(f'== {f}  B&H avg/day {bh*100:.3f}%   (cols: per-day-in-mkt ret | IS 2000-12 avg,t | OOS 2013-26 avg,t)')
    rules={'IBS<0.2 next close':(lambda d,i:d.ibs.iat[i]<0.2,nxt),
           'IBS<0.2 exit IBS>0.8':(lambda d,i:d.ibs.iat[i]<0.2,lambda d,i,j:d.ibs.iat[j]>0.8),
           'IBS<0.2 exit >prevH':(lambda d,i:d.ibs.iat[i]<0.2,up_exit)}
    for x in (0.2,0.25,0.3,0.35,0.4,0.5):
        rules[f'DOUBLE<{x} next close']=(dbl(x),nxt); rules[f'DOUBLE<{x} exit >prevH']=(dbl(x),up_exit)
    for k,(e,x) in rules.items():
        t=run(d,e,x,cost_pts=cost); r=t.r; isx=t.entry<'2013'
        f2=lambda s:f'{s.mean()*100:+.3f}% t{s.mean()/s.std()*np.sqrt(len(s)):+.1f} n{len(s)}'
        print(f'  {k:24s} {r.sum()/t.bars.sum()*100:+.3f}%/day ({r.sum()/t.bars.sum()/bh:4.1f}x B&H) | IS {f2(r[isx])} | OOS {f2(r[~isx])}')
