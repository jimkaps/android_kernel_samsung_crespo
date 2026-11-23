import sys, runpy, numpy as np, pandas as pd
sys.argv = ["x", "upload/NQ_5m_2020.csv", "work", "kane"]
# reuse definitions without re-running analysis: exec file up to the trade loop
src = open("kane/ict_conf.py").read().split("import os\ntrades")[0]
g = {}; exec(src, g)
idx, fvgs, trade, ctx, days, L, H, O, mins = (g[k] for k in ["idx", "fvgs", "trade", "ctx", "days", "L", "H", "O", "mins"])
SPLIT = g["SPLIT"]
def sb(d, rule, a=600, z=660, pen=0.0, minsz=3):
    w = idx(d, a, z)
    if len(w) < 3: return None
    for i, s, bot, top, c1 in fvgs(w[0], w[-1] + 1):
        if top - bot < minsz: continue
        ce = (bot + top) / 2; stop = c1 - 1 if s == 1 else c1 + 1
        rest = idx(d, mins[i] + 5, z)
        hit = [j for j in rest if (L[j] <= ce - pen if s == 1 else H[j] >= ce + pen)]
        if not hit: continue
        e = hit[0]; entry = min(O[e], ce) if s == 1 else max(O[e], ce)
        return trade(d, s, e, entry, stop, rule, True)
    return None
def go(label, **kw):
    t = pd.DataFrame([x for d in days[21:] if (x := sb(d, kw.pop("rule", "2R") if False else kw.get("rule", "2R"), **{k: v for k, v in kw.items() if k != "rule"}))]).join(ctx, on="date")
    for f, gsel in [("all", np.ones(len(t), bool)), ("with trend", (t.side == t.trend).values)]:
        x = t[gsel]; a, b = x[x.date < SPLIT], x[x.date >= SPLIT]
        ts = lambda y: y.mean() / y.std() * np.sqrt(len(y))
        print(f"{label:34s} {f:10s} n={len(x):4d} R_tr={a.R.mean():+.3f} (t {ts(a.R):+.2f})  R_te={b.R.mean():+.3f} (t {ts(b.R):+.2f})  $/yr={x.pts.sum()*2/6.8:+6.0f}")
    return t
t = go("base 10-11, 2R", rule="2R")
go("cost 3pt (+1.5)", rule="2R") if False else None
x = t[t.side == t.trend].copy(); x["y"] = pd.to_datetime(x.date).dt.year
print("with-trend by year $:", (x.groupby("y").pts.sum() * 2).round(0).to_dict())
print("with-trend by side avgR:", x.groupby("side").R.mean().round(3).to_dict(), x.groupby("side").size().to_dict())
print("with-trend at 3pt cost: avgR", round(((x.pts - 1.5) / x.risk).mean(), 3), " $/yr", round((x.pts - 1.5).sum() * 2 / 6.8))
print("with-trend avg risk pts", round(x.risk.mean(), 1))
go("limit needs 1pt trade-through", rule="2R", pen=1.0)
go("1R", rule="1R"); go("3R", rule="3R")
go("FVG >= 6 pts", rule="2R", minsz=6)
go("window 10:00-10:30", rule="2R", z=630)
go("PM silver bullet 14-15", rule="2R", a=840, z=900)
go("London 03-04", rule="2R", a=180, z=240)
