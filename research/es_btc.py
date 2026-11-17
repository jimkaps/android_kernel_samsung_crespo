import sys, numpy as np, pandas as pd
def load(f):
    d=pd.read_csv(f,index_col=0,parse_dates=True)[['Open','High','Low','Close']].dropna()
    d=d[d.High>d.Low]
    if d.index[-1]>=pd.Timestamp('2026-11-16'): d=d.iloc[:-1]
    d['ibs']=(d.Close-d.Low)/(d.High-d.Low); return d
def trades(d,thr=0.3,single=0.1):
    C,ibs=d.Close.values,d.ibs.values; out=[]; i=1; n=len(d)
    while i<n-1:
        sig=(ibs[i]<thr and ibs[i-1]<thr) or (single is not None and ibs[i]<single)
        if sig:
            j=i+1
            while j<n-1 and ((ibs[j]<thr and ibs[j-1]<thr) or (single is not None and ibs[j]<single)): j+=1   # HOLD if signal fires again
            out.append((d.index[i],d.index[j],C[j]/C[i]-1)); i=j+1
        else: i+=1
    t=pd.DataFrame(out,columns=['date','exit','r']); t['nights']=(t.exit-t.date).dt.days; return t
EXPO=2000.0
COSTS={ # per-trade fraction of exposure, financing per night, FX on pnl
 'cfd_index':dict(rt=0.0002,fin=0.065/365,fx=0.005),
 'btc_spot': dict(rt=0.0030,fin=0.0,fx=0.0),        # crypto exchange/ETN: ~0.15% each way, no overnight fee
 'btc_cfd':  dict(rt=0.0060,fin=0.18/365,fx=0.005), # typical crypto CFD (not offered to UK retail)
}
def gbp(t,c):
    g=t.r*EXPO; return g-np.abs(g)*c['fx']-EXPO*c['rt']-EXPO*c['fin']*t.nights
def stats(t,c,label):
    if len(t)<5: return None
    p=gbp(t,c); eq=p.cumsum(); dd=(eq-eq.cummax()).min()
    yrs=(t.exit.iloc[-1]-t.date.iloc[0]).days/365.25
    yr=p.groupby(t.exit.dt.year).sum()
    ts=t.r.mean()/t.r.std()*np.sqrt(len(t))
    return dict(set=label,trades_yr=round(len(t)/yrs,1),win=f"{(p>0).mean():.0%}",gross_avg_pct=round(t.r.mean()*100,3),t_stat=round(ts,2),
                gbp_yr=round(p.sum()/yrs),worst_dd=round(dd),worst_trade=round(p.min()),neg_years=f"{(yr<0).sum()}/{len(yr)}")
pd.set_option('display.width',250); pd.set_option('display.max_columns',20)
rows=[]
for f,cost,start,split in [('QQQ.csv','cfd_index','2010','2018'),('SPY.csv','cfd_index','2010','2018'),('ES_F.csv','cfd_index','2010','2018'),
                           ('SPY.csv','cfd_index','2000','2013'),('GSPC.csv','cfd_index','1990','2008'),
                           ('BTC.csv','btc_spot','2015','2021'),('BTC.csv','btc_cfd','2015','2021')]:
    d=load(f); d=d[d.index>=start]; t=trades(d)
    for lab,tt in [('all',t),(f'<{split}',t[t.date<split]),(f'>={split}',t[t.date>=split])]:
        s=stats(tt.reset_index(drop=True),COSTS[cost],lab)
        if s: rows.append(dict(mkt=f[:-4],costs=cost,from_=start,**s))
print(pd.DataFrame(rows).to_string(index=False))
print("\nNext-day gross return (%) by today's IBS bucket, and hit rate:")
for f,start in [('SPY.csv','2005'),('ES_F.csv','2005'),('BTC.csv','2015'),('BTC.csv','2021')]:
    d=load(f); d=d[d.index>=start]; nr=d.Close.pct_change().shift(-1)
    b=pd.cut(d.ibs,[0,.1,.2,.3,.5,.7,.9,1],include_lowest=True)
    g=nr.groupby(b,observed=True).agg(['mean','count']); g['mean']*=100
    print(f, start, ' | '.join(f"{i}: {r['mean']:+.3f} (n={int(r['count'])})" for i,r in g.iterrows()))
print("\nBTC threshold sensitivity (btc_spot costs, 2015-2026, £/yr):")
d=load('BTC.csv'); d=d[d.index>='2015']
for thr in (0.2,0.25,0.3,0.35,0.4):
    for single in (None,0.1):
        t=trades(d,thr,single); p=gbp(t,COSTS['btc_spot']); yrs=(t.exit.iloc[-1]-t.date.iloc[0]).days/365.25
        e=t.date>='2021'; p2=p[e]; y2=(t.exit.iloc[-1]-pd.Timestamp('2021-01-01')).days/365.25
        print(f"  dbl<{thr} {'|<0.1' if single else '     '}: all £{p.sum()/yrs:+5.0f}/yr  2021+ £{p2.sum()/y2:+5.0f}/yr  trades/yr {len(t)/yrs:.0f}")
