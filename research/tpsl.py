import numpy as np, pandas as pd
from ibs_bt import load
q = load('QQQ.csv'); nq = load('NQ_F.csv')
q = q[q.index >= '2010']; nq = nq.reindex(q.index).ffill()
sig = ((q.ibs < .3) & (q.ibs.shift() < .3)) | (q.ibs < .1)
S = sig.values; O,H,L,C = (nq[c].values for c in 'Open High Low Close'.split()); idx = q.index
EXPO, SPREAD, MANUAL, FUND, FX = 2000, 1e-4, 1e-4, .065/365, .005
def sim(sl, tp):
    out=[]; i=0; n=len(q)
    while i < n-1:
        if not S[i]: i+=1; continue
        e=C[i]; lo=e*(1-sl) if sl else -1; hi=e*(1+tp) if tp else 1e18; j=i+1; how='close'
        while True:
            if O[j]<=lo: x=O[j]; how='sl'; break
            if O[j]>=hi: x=O[j]; how='tp'; break
            if L[j]<=lo: x=lo; how='sl'; break          # if both hit same day, assume the stop came first
            if H[j]>=hi: x=hi; how='tp'; break
            if S[j] and j<n-1: j+=1; continue            # signal again: keep holding
            x=C[j]; break
        r=x/e-1; nights=(idx[j]-idx[i]).days; g=r*EXPO
        out.append((idx[j], g-abs(g)*FX-EXPO*(SPREAD+MANUAL)-EXPO*FUND*nights, how)); i=j+1 if how!='close' else j
    t=pd.DataFrame(out,columns=['exit','gbp','how']); eq=t.gbp.cumsum(); yrs=(idx[-1]-idx[0]).days/365.25
    return dict(sl=f'{sl:.1%}' if sl else '-', tp=f'{tp:.2%}' if tp else '-', per_yr=eq.iloc[-1]/yrs, dd=(eq-eq.cummax()).min(),
                worst=t.gbp.min(), win=(t.gbp>0).mean(), sl_hits=(t.how=='sl').mean(), tp_hits=(t.how=='tp').mean())
rows=[sim(s,t) for s in (0,.01,.015,.02,.03,.04) for t in (0,.005,.0075,.01,.015,.02,.03)]
r=pd.DataFrame(rows); pd.set_option('display.width',200); print(r.round(2).to_string(index=False))
