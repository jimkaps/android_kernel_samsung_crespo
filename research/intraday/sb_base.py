import sys, numpy as np, pandas as pd
sys.argv = ["x", "upload/NQ_5m_2020.csv", "work", "kane"]
src = open("kane/ict_conf.py").read().split("import os\ntrades")[0]; g = {}; exec(src, g)
idx, trade, ctx, days, O, C = (g[k] for k in ["idx", "trade", "ctx", "days", "O", "C"]); SPLIT = g["SPLIT"]
t = pd.read_pickle("kane/ict_trades.pkl")[("SilverBullet 10-11", "2R")]; x = t[t.side == t.trend]
eq = x.pts.cumsum() * 2; print("SB+trend: all-period t", round(x.R.mean() / x.R.std() * np.sqrt(len(x)), 2), " maxDD $", round((eq - eq.cummax()).min()), " trades/yr", round(len(x) / 6.8))
# baseline: same days/side/risk, but enter at a random 5m bar between 10:00 and 11:00 (market at its open), stop = same risk, 2R
rng = np.random.default_rng(0); res = []
for rep in range(20):
    rr = []
    for _, row in x.iterrows():
        w = idx(row.date, 600, 660); e = rng.choice(w); s = row.side; entry = O[e]
        y = trade(row.date, s, e, entry, entry - s * row.risk, "2R", True)
        if y: rr.append(y)
    b = pd.DataFrame(rr); res.append((b.R.mean(), b[b.date < SPLIT].R.mean(), b[b.date >= SPLIT].R.mean()))
res = np.array(res); print("random-entry same days/side/stop: avgR all %.3f (range %.3f..%.3f), train %.3f, test %.3f" % (res[:,0].mean(), res[:,0].min(), res[:,0].max(), res[:,1].mean(), res[:,2].mean()))
print("SB+trend avgR all %.3f train %.3f test %.3f" % (x.R.mean(), x[x.date < SPLIT].R.mean(), x[x.date >= SPLIT].R.mean()))
