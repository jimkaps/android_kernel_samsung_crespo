import itertools, pandas as pd
from funded import load, evaluate
q=load(); IS=q[(q.index>='2005')&(q.index<'2017')]; OOS=q[q.index>='2017']; FULL=q[q.index>='2005']
G=dict(dbl=[0.3,0.35,0.4],single=[0.0,0.1],stop=[0.01,0.015,0.02,0.05],n_eval=[1,2,3],n_fund=[1,2],keep=[0.0,500.0,1000.0,1500.0],tp=[0.0,0.01,0.015])
rows=[]
for c in itertools.product(*G.values()):
    kw=dict(zip(G,c)); r=evaluate(IS,k=0.0,n_acc=2000,**kw); rows.append({**kw,**r})
res=pd.DataFrame(rows).sort_values('ev_yr',ascending=False); pd.set_option('display.width',220)
print('top 12 IS 2005-16:'); print(res.head(12).round(2).to_string(index=False))
out=[]
for _,r in res.head(12).iterrows():
    kw={c:r[c] for c in G}; o=evaluate(OOS,k=0.0,n_acc=6000,seed=3,**kw); out.append({**kw,**o})
print('\nsame, OOS 2017-26:'); print(pd.DataFrame(out).round(2).to_string(index=False))
# robustness of the chosen family on OOS: marginal effect of each lever
best=res.iloc[0]; base={c:best[c] for c in G}
print('\nOOS sensitivity around IS-best', base)
for c in G:
    print(' ',c, {v: round(evaluate(OOS,k=0.0,n_acc=6000,seed=4,**{**base,c:v})['ev_yr']) for v in G[c]})
