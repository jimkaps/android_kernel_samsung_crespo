import sys, numpy as np, pandas as pd
sys.argv=["x"]; exec(open("idx/improve2.py").read().split("pd.set_option")[0])
T = pd.read_pickle("idx/market_trades.pkl")
def pst(parts, w, a, b):
    yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    daily = pd.concat([T[p].assign(gbp=T[p].gbp * wi).groupby("exit").gbp.sum() for p, wi in zip(parts, w)], axis=1).fillna(0).sum(1)
    daily = daily[(daily.index >= a) & (daily.index < b)]; e = daily.cumsum(); dd = (e - e.cummax()).min(); py = daily.sum() / yrs
    n = sum(((T[p].date >= a) & (T[p].date < b)).sum() for p in parts) / yrs
    return n, py, dd, py / -dd * 1000
rows = []
for nm, parts, w in [("QQQ only £2,000 (current)", ["QQQ (US100)"], [1]),
                     ("QQQ £2,000 + IWM £2,000", ["QQQ (US100)", "IWM (US2000)"], [1, 1]),
                     ("QQQ £1,000 + IWM £1,000", ["QQQ (US100)", "IWM (US2000)"], [.5, .5]),
                     ("QQQ + SPY + IWM, £2,000 each", ["QQQ (US100)", "SPY (US500)", "IWM (US2000)"], [1, 1, 1]),
                     ("QQQ £2,000 + Nikkei £2,000", ["QQQ (US100)", "Nikkei (JP225)"], [1, 1]),
                     ("QQQ + IWM + Nikkei, £2,000 each", ["QQQ (US100)", "IWM (US2000)", "Nikkei (JP225)"], [1, 1, 1])]:
    a = pst(parts, w, "2001-01-01", "2015-01-01"); b = pst(parts, w, "2015-01-01", "2026-11-23")
    rows.append([nm, *np.round(a, 1), "|", *np.round(b, 1)])
print(pd.DataFrame(rows, columns=["portfolio", "tr/yr", "£/yr", "DD", "score", "|", "tr/yr", "£/yr", "DD", "score"]).to_string(index=False))
# breadth sizing: bigger QQQ position when SPY and IWM are also signalling
q = feats(load("work/QQQ.csv")); s = feats(load("work/SPY.csv")); i_ = feats(load("idx/IWM.csv"))
S0 = sig_cur(q); oth = (sig_cur(s).reindex(q.index).fillna(False).astype(int) + sig_cur(i_).reindex(q.index).fillna(False).astype(int))
for nm, sz in [("breadth: 1.5x if both SPY & IWM also signal", np.where(oth.values == 2, 1.5, 1.0)), ("breadth: 0.5x if neither signals", np.where(oth.values == 0, .5, 1.0))]:
    print(nm, row(nm, run(q, S0, size=sz)))
