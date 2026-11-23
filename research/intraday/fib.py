"""Fib confluence: is the entry price at a Fibonacci level of the previous day's / previous week's RTH range?
Every method x fib filter (alone, and + one other filter). Search 2020-24, final 2025-26, luck benchmark."""
import sys, itertools, numpy as np, pandas as pd
sys.argv = ["x", "upload/NQ_5m_2020.csv", "work", "kane"]
src = open("kane/ict_conf.py").read().split("# ---------- trade engine")[0]; g = {}; exec(src, g); ctx, rth = g["ctx"], g["rth"]
wk = pd.Series(pd.to_datetime(rth.index)).dt.to_period("W").values
w = rth.assign(wk=wk).groupby("wk").agg(h=("h", "max"), l=("l", "min"))
pw = w.shift(1); ctx["pwh"] = [pw.h.get(p, np.nan) for p in wk]; ctx["pwl"] = [pw.l.get(p, np.nan) for p in wk]
CUT = pd.Timestamp("2025-01-01").date()
sets = []
for (tf, st, ex, f), t in pd.read_pickle("nqy/strat_long_trades.pkl").items():
    ti = pd.DatetimeIndex(t.time); sets.append((f"Strat {tf} {st} {ex}{' FTFC' if f else ''}",
        pd.DataFrame(dict(date=ti.date, side=t.side.values, entry=t.entry.values, R=t.R.values, pts=t.pts.values, t=(ti.hour * 60 + ti.minute).values))))
for key, t in pd.read_pickle("kane/kane_trades.pkl").items():
    if key[0] == "A" and key[4] != "none": continue
    sets.append(("Kane " + " ".join(map(str, key)), pd.DataFrame(dict(date=t.date, side=t.side, entry=t.entry, R=t.R, pts=t.pts, t=np.nan))))
for (nm, rule), t in pd.read_pickle("kane/ict_trades.pkl").items():
    sets.append((f"ICT {nm} {rule}", t[["date", "side", "entry", "R", "pts", "t"]].copy()))
TOL = 0.03   # within 3% of the range from the level
def fibpos(x, hi, lo):   # retracement measured from the trade's favourable end: longs from the high down, shorts from the low up
    return np.where(x.side == 1, (x[hi] - x.entry) / (x[hi] - x[lo]), (x.entry - x[lo]) / (x[hi] - x[lo]))
FIB = {}
for rg, hi, lo in [("prev day", "pdh", "pdl"), ("prev week", "pwh", "pwl")]:
    for lv in [0.382, 0.5, 0.618, 0.705, 0.786]:
        FIB[f"{rg} fib {lv}"] = (lambda hi, lo, lv: lambda x: np.abs(fibpos(x, hi, lo) - lv) <= TOL)(hi, lo, lv)
    FIB[f"{rg} any fib"] = (lambda hi, lo: lambda x: np.min([np.abs(fibpos(x, hi, lo) - l) for l in [0.382, 0.5, 0.618, 0.705, 0.786]], 0) <= TOL)(hi, lo)
    FIB[f"{rg} OTE 0.62-0.79"] = (lambda hi, lo: lambda x: (fibpos(x, hi, lo) >= 0.62) & (fibpos(x, hi, lo) <= 0.79))(hi, lo)
    FIB[f"{rg} discount/premium"] = (lambda hi, lo: lambda x: fibpos(x, hi, lo) >= 0.5)(hi, lo)   # long below 50%, short above
OTHER = {"with 20d trend": lambda x: x.side == x.trend, "against 20d trend": lambda x: x.side == -x.trend,
         "IBS agrees": lambda x: ((x.side == 1) & (x.ibs < .3)) | ((x.side == -1) & (x.ibs > .7)),
         "high vol": lambda x: x.hivol == 1, "low vol": lambda x: x.hivol == 0, "longs": lambda x: x.side == 1, "shorts": lambda x: x.side == -1,
         "daily SMT agrees": lambda x: x.side == x.smt, "VIX>20": lambda x: x.vix > 20}
combos = [(f,) for f in FIB] + [(f, o) for f in FIB for o in OTHER]
alldays = sorted(set(ctx.index)); dpos = {d: i for i, d in enumerate(alldays)}
flips = np.random.default_rng(2).choice([-1, 1], size=(10, len(alldays)))
rows = []; null_best = np.full(10, -np.inf); null_cnt = np.zeros(10)
def tst(Mx, r):
    n = Mx.sum(1); mu = (Mx @ r) / np.maximum(n, 1); sd = np.sqrt(np.maximum((Mx @ (r * r)) / np.maximum(n, 1) - mu ** 2, 1e-12)); return mu, mu / sd * np.sqrt(n)
for name, t in sets:
    t = t.join(ctx, on="date"); t = t[t.date.map(lambda d: d in dpos)].reset_index(drop=True)
    allF = {**FIB, **OTHER}; base = {k: np.nan_to_num(np.asarray(v(t), float)).astype(bool) for k, v in allF.items()}
    srch = (t.date < CUT).values; R = t.R.values; P = t.pts.values; di = t.date.map(dpos).values
    M = np.array([np.logical_and.reduce([base[c] for c in cb]) for cb in combos]); Ms, Mh = M & srch, M & ~srch
    ns, nh = Ms.sum(1), Mh.sum(1); ok = (ns >= 60) & (nh >= 15)
    mu_s, t_s = tst(Ms, R); mu_h, t_h = tst(Mh, R)
    b_s, bt_s = tst(srch[None, :], R); b_h, _ = tst((~srch)[None, :], R)
    for k in np.where(ok)[0]:
        rows.append((name, " + ".join(combos[k]), ns[k], mu_s[k], t_s[k], nh[k], mu_h[k], t_h[k], (P * Mh[k]).sum() * 2 / 1.85, b_s[0], b_h[0]))
    Rc = R - R[srch].mean()
    for r_ in range(10):
        _, tn = tst(Ms, Rc * flips[r_, di]); tn = np.where(ok, tn, -np.inf); null_best[r_] = max(null_best[r_], tn.max()); null_cnt[r_] += (tn > 3).sum()
r = pd.DataFrame(rows, columns=["method", "filters", "n_search", "R_search", "t_search", "n_final", "R_final", "t_final", "usd_yr_final", "base_R_search", "base_R_final"])
r.to_csv("kane/fib_results.csv", index=False)
pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 50)
print("strategies tested:", len(r))
print("REAL best t %.2f, count t>3: %d | LUCK best t per scramble %s, avg count t>3 %.0f" % (r.t_search.max(), (r.t_search > 3).sum(), np.round(null_best, 2), null_cnt.mean()))
# does adding a fib filter improve on the method without it?  (fib-only rows)
fo = r[~r.filters.str.contains(" \\+ ")].copy(); fo["lift_s"] = fo.R_search - fo.base_R_search; fo["lift_f"] = fo.R_final - fo.base_R_final
print("\nFib filter alone - average improvement vs the same method without it (R per trade):")
print(fo.groupby("filters")[["lift_s", "lift_f"]].agg(["mean"]).round(3).assign(n=fo.groupby("filters").size()).to_string())
top = r.sort_values("t_search", ascending=False)
print("\nTOP 15 in 2020-24 and their locked 2025-26 result:"); print(top.head(15).drop(columns=["base_R_search", "base_R_final"]).round(2).to_string(index=False))
for k in [10, 50, 200]:
    tk = top.head(k); print(f"top {k}: R search {tk.R_search.mean():+.3f} -> final {tk.R_final.mean():+.3f}; profitable in final {(tk.R_final > 0).mean():.2f}")
