import numpy as np, pandas as pd
from ibs_bt import load
q = load('QQQ.csv'); q = q[q.index >= '2010']
S=(((q.ibs<.3)&(q.ibs.shift()<.3))|(q.ibs<.1)).values; O,C=q.Open.values,q.Close.values; idx=q.index
def run(mode):
    out=[]; i=0; n=len(q)
    while i<n-1:
        if not S[i]: i+=1; continue
        j=i+1
        while S[j] and j<n-1 and mode=='close': j+=1
        x={'close':C[j],'open':O[j],'mid':(O[j]+C[j])/2}[mode]
        g=(x/C[i]-1)*2000; nights=(idx[j]-idx[i]).days
        out.append(g-abs(g)*.005-2000*2e-4-2000*.065/365*nights); i=j if mode=='close' else j  # re-check signal day j
    t=np.array(out); eq=t.cumsum(); yrs=(idx[-1]-idx[0]).days/365.25
    print(f"{mode:6s} £{eq[-1]/yrs:6.0f}/yr  DD £{(eq-np.maximum.accumulate(eq)).min():.0f}  win {np.mean(t>0):.0%}")
for m in ('close','open','mid'): run(m)
