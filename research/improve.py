import numpy as np, pandas as pd
EXPO=2000.0; RT=0.0002; FIN=0.065/365; FX=0.005
def load(f):
    d=pd.read_csv(f,index_col=0,parse_dates=True)[['Open','High','Low','Close']].dropna(); d=d[d.High>d.Low]
    if d.index[-1]>=pd.Timestamp('2026-11-16'): d=d.iloc[:-1]
    return d
def feats(d,other,vix):
    d=d.copy(); d['ibs']=(d.Close-d.Low)/(d.High-d.Low); d['ibs1']=d.ibs.shift(1)
    ch=d.Close.diff(); up=ch.clip(lower=0).ewm(alpha=.5).mean(); dn=(-ch.clip(upper=0)).ewm(alpha=.5).mean(); d['rsi2']=100-100/(1+up/dn)
    d['sma200']=d.Close.rolling(200).mean(); d['sma5']=d.Close.rolling(5).mean()
    d['low5']=d.Close<d.Close.shift(1).rolling(4).min()
    o=(other.Close-other.Low)/(other.High-other.Low); d['oibs']=o.reindex(d.index); d['oibs1']=d.oibs.shift(1)
    d['vix']=vix.Close.reindex(d.index).ffill(); d['vixma']=d.vix.rolling(20).mean()
    d['dow']=d.index.dayofweek; d['prevH']=d.High.shift(1)
    return d.dropna()
def base(d,thr=.3,s=.1): return ((d.ibs<thr)&(d.ibs1<thr))|(d.ibs<s)
def run(d,sig,exit_rule=None,maxh=5):
    S=sig.values; C=d.Close.values; out=[]; i=0; n=len(d)
    while i<n-1:
        if S[i]:
            j=i+1
            if exit_rule is None:
                while j<n-1 and S[j]: j+=1
            else:
                E=exit_rule
                while j<n-1 and not E[j] and j-i<maxh: j+=1
            out.append((d.index[i],d.index[j],C[j]/C[i]-1)); i=j+1
        else: i+=1
    t=pd.DataFrame(out,columns=['date','exit','r']); t['n']=(t.exit-t.date).dt.days
    t['gbp']=t.r*EXPO-np.abs(t.r*EXPO)*FX-EXPO*RT-EXPO*FIN*t.n; return t
def st(t,a,b):
    t=t[(t.date>=a)&(t.date<b)]; yrs=(pd.Timestamp(b)-pd.Timestamp(a)).days/365.25
    if len(t)<10: return (len(t)/yrs,np.nan,np.nan,np.nan,np.nan)
    e=t.gbp.cumsum(); dd=(e-e.cummax()).min(); py=t.gbp.sum()/yrs
    return (len(t)/yrs, py, dd, t.gbp.mean()/t.gbp.std()*np.sqrt(len(t)), py/-dd*1000 if dd<0 else np.nan)
vix=load('VIX.csv') if False else pd.read_csv('VIX.csv',index_col=0,parse_dates=True)
M={'NQ (QQQ)':feats(load('QQQ.csv'),load('SPY.csv'),vix),'ES (SPY)':feats(load('SPY.csv'),load('QQQ.csv'),vix)}
def variants(d):
    B=base(d)
    hiexit=(d.Close>d.prevH).values
    return {
     '0 BASE (current rule)':(B,None),
     'F1 + above 200-day avg':(B&(d.Close>d.sma200),None),
     'F2 + below 200-day avg':(B&(d.Close<d.sma200),None),
     'F3 + VIX above its 20d avg':(B&(d.vix>d.vixma),None),
     'F4 + VIX > 20':(B&(d.vix>20),None),
     'F5 + close below 5-day avg':(B&(d.Close<d.sma5),None),
     'F6 + other index also weak':(B&(((d.oibs<.3)&(d.oibs1<.3))|(d.oibs<.1)),None),
     'F7 + no Friday entries':(B&(d.dow!=4),None),
     'M1 base OR RSI2<10':(B|(d.rsi2<10),None),
     'M2 base OR new 5-day low & IBS<.5':(B|(d.low5&(d.ibs<.5)),None),
     'M3 looser: dbl<.4 or <.15':(base(d,.4,.15),None),
     'M4 single IBS<.2':(d.ibs<.2,None),
     'M5 RSI2<10 alone':(d.rsi2<10,None),
     'X1 exit when close>prev high (max5)':(B,hiexit),
     'X2 exit when IBS>.5 (max5)':(B,(d.ibs>.5).values),
     'X3 fixed 2-day hold':(B,np.zeros(len(d),bool)),
    }
pd.set_option('display.width',250)
for name,d in M.items():
    rows=[]
    for v,(sig,ex) in variants(d).items():
        t=run(d,sig,ex,maxh=(2 if v.startswith('X3') else 5))
        a=st(t,'2001-01-01','2015-01-01'); b=st(t,'2015-01-01','2026-11-16')
        rows.append([v,*[round(x,1) if i in(0,3) else (round(x) if x==x else x) for i,x in enumerate(a)],'|',*[round(x,1) if i in(0,3) else (round(x) if x==x else x) for i,x in enumerate(b)]])
    print(f"\n=== {name}, £2,000 per trade after CFD costs.  TRAIN 2001-2014  |  TEST 2015-2026   (score = £/yr per £1,000 of worst drawdown)")
    print(pd.DataFrame(rows,columns=['variant','tr/yr','£/yr','DD','t','score','|','tr/yr','£/yr','DD','t','score']).to_string(index=False))
