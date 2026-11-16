import numpy as np, pandas as pd
from ibs_bt import load
def trades(d, thr, rule, cost_pct, single=None):
    C,H,ibs=d.Close.values,d.High.values,d.ibs.values; out=[]; i=1; n=len(d)
    while i<n-1:
        sig = ibs[i]<thr and ibs[i-1]<thr
        if single is not None: sig = sig or ibs[i]<single
        if sig:
            j=i+1
            if rule=='prevH':
                while j<n-1 and not C[j]>H[j-1] and j-i<10: j+=1
            out.append((d.index[i], C[j]/C[i]-1-cost_pct, j-i)); i=j
        else: i+=1
    return pd.DataFrame(out,columns=['date','r','bars'])
def summarize(t, start='2005'):
    t=t[t.date>=start]; yrs=(t.date.iloc[-1]-t.date.iloc[0]).days/365.25
    eq=(1+t.r).cumprod(); dd=(eq/eq.cummax()-1).min()                # 100% of account per trade, compounding
    add=t.r.cumsum(); add_dd=(add-add.cummax()).min()                 # fixed 1 unit (futures-like), % of notional
    ts=t.r.mean()/t.r.std()*np.sqrt(len(t))
    yr=t.groupby(t.date.dt.year).r.sum()
    return dict(n_yr=len(t)/yrs, win=(t.r>0).mean(), avg=t.r.mean()*100, t=ts, cagr=(eq.iloc[-1]**(1/yrs)-1)*100, dd=dd*100,
                worst=t.r.min()*100, add_dd=add_dd*100, neg_yrs=f'{(yr<0).sum()}/{len(yr)}', inmkt=t.bars.sum()/(yrs*252))
COST={'ES_F.csv':1.25/7558*0+0.00012,'SPY.csv':0.0002,'GC_F.csv':0.00015,'GLD.csv':0.0003,'QQQ.csv':0.0002,'NQ_F.csv':0.0001}
rows=[]
for f in COST:
    d=load(f)
    for thr,rule,single in [(0.3,'next',None),(0.35,'next',None),(0.4,'next',None),(0.3,'prevH',None),(0.4,'prevH',None),(0.3,'next',0.1)]:
        s=summarize(trades(d,thr,rule,COST[f],single)); rows.append(dict(mkt=f[:-4],rule=f'dbl<{thr}'+(f'|<{single}' if single else '')+f' {rule}',**s))
r=pd.DataFrame(rows); pd.set_option('display.width',220)
print('2005-2026. cagr/dd = putting 100% of the account into each trade (1x, no leverage). add_dd = worst DD in % of 1 contract notional.')
print(r.round(2).to_string(index=False))
