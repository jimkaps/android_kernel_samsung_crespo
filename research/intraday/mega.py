"""Every method x every confluence filter (up to 3 at once) on NQ 2020-2026.
Search on 2020-2024 only; 2025-2026 locked as the final test. Luck benchmark: same search with outcomes scrambled by day."""
import sys, itertools, numpy as np, pandas as pd
sys.argv = ["x", "upload/NQ_5m_2020.csv", "work", "kane"]
src = open("kane/ict_conf.py").read().split("# ---------- trade engine")[0]; g = {}; exec(src, g); ctx = g["ctx"]
CUT = pd.Timestamp("2025-01-01").date()
sets = []
for (tf, st, ex, f), t in pd.read_pickle("nqy/strat_long_trades.pkl").items():
    ti = pd.DatetimeIndex(t.time); sets.append((f"Strat {tf} {st} {ex}{' FTFC' if f else ''}",
        pd.DataFrame(dict(date=ti.date, side=t.side.values, R=t.R.values, pts=t.pts.values, t=(ti.hour * 60 + ti.minute).values))))
for key, t in pd.read_pickle("kane/kane_trades.pkl").items():
    if key[0] == "A" and key[4] != "none": continue
    sets.append(("Kane " + " ".join(map(str, key)), pd.DataFrame(dict(date=t.date, side=t.side, R=t.R, pts=t.pts, t=np.nan))))
for (nm, rule), t in pd.read_pickle("kane/ict_trades.pkl").items():
    sets.append((f"ICT {nm} {rule}", t[["date", "side", "R", "pts", "t"]].copy()))
F = {
    "with 20d trend": lambda x: x.side == x.trend, "against 20d trend": lambda x: x.side == -x.trend,
    "IBS agrees": lambda x: ((x.side == 1) & (x.ibs < .3)) | ((x.side == -1) & (x.ibs > .7)),
    "RSI2 agrees": lambda x: ((x.side == 1) & (x.rsi2 < 30)) | ((x.side == -1) & (x.rsi2 > 70)),
    "high vol": lambda x: x.hivol == 1, "low vol": lambda x: x.hivol == 0,
    "VIX>20": lambda x: x.vix > 20, "VIX<=20": lambda x: x.vix <= 20,
    "with gap": lambda x: (x.side == x.gap) & (x.t >= 570), "fade gap": lambda x: (x.side == -x.gap) & (x.t >= 570),
    "daily SMT agrees": lambda x: x.side == x.smt, "NQ>ES strength agrees": lambda x: x.side == x.rs5,
    "longs": lambda x: x.side == 1, "shorts": lambda x: x.side == -1,
    "9:30-10:30": lambda x: (x.t >= 570) & (x.t < 630), "10:30-12": lambda x: (x.t >= 630) & (x.t < 720),
    "12-14": lambda x: (x.t >= 720) & (x.t < 840), "14-16": lambda x: (x.t >= 840) & (x.t < 960),
    "Mon-Tue": lambda x: x.dow <= 1, "Wed-Thu": lambda x: (x.dow >= 2) & (x.dow <= 3), "Fri": lambda x: x.dow == 4,
}
names = list(F)
combos = [()] + [(a,) for a in names] + list(itertools.combinations(names, 2)) + list(itertools.combinations(names, 3))
print("sets", len(sets), "filter combos", len(combos), "=> up to", len(sets) * len(combos), "strategies", flush=True)
alldays = sorted(set(ctx.index)); dpos = {d: i for i, d in enumerate(alldays)}
rng = np.random.default_rng(1); REPS = 10
flips = rng.choice([-1, 1], size=(REPS, len(alldays)))
rows = []; null_best = np.full(REPS, -np.inf); null_tests = []
for name, t in sets:
    t = t.join(ctx, on="date"); t = t[t.date.map(lambda d: d in dpos)]
    t["dow"] = pd.to_datetime(t.date).dt.dayofweek
    base = {n: np.asarray(F[n](t), bool) for n in names}
    srch = (t.date < CUT).values; R = t.R.values; P = t.pts.values; di = t.date.map(dpos).values
    M = np.array([np.logical_and.reduce([base[c] for c in cb]) if cb else np.ones(len(t), bool) for cb in combos])
    Ms, Mh = M & srch, M & ~srch
    ns, nh = Ms.sum(1), Mh.sum(1)
    def tst(Mx, r):
        n = Mx.sum(1); s1 = Mx @ r; s2 = Mx @ (r * r); mu = s1 / np.maximum(n, 1)
        sd = np.sqrt(np.maximum(s2 / np.maximum(n, 1) - mu ** 2, 1e-12)); return mu, mu / sd * np.sqrt(n)
    mu_s, t_s = tst(Ms, R); mu_h, t_h = tst(Mh, R)
    ok = (ns >= 60) & (nh >= 15)
    for k in np.where(ok)[0]:
        rows.append((name, " + ".join(combos[k]) or "none", ns[k], mu_s[k], t_s[k], nh[k], mu_h[k], t_h[k], (P * Mh[k]).sum() * 2 / 1.85))
    # luck benchmark: R minus its set mean, sign flipped by day (same flip for every strategy on a day) -> no real edge
    Rc = R - R[srch].mean()
    for r_ in range(REPS):
        _, tn = tst(Ms, Rc * flips[r_, di]); tn = np.where(ok, tn, -np.inf); null_best[r_] = max(null_best[r_], tn.max())
        if r_ == 0: null_tests.append(tn[ok])
r = pd.DataFrame(rows, columns=["method", "filters", "n_search", "R_search", "t_search", "n_final", "R_final", "t_final", "usd_yr_final"])
r.to_csv("kane/mega_results.csv", index=False)
nt = np.concatenate(null_tests)
pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 55); pd.set_option("display.max_rows", 100)
print("strategies tested:", len(r))
print("REAL search: best t = %.2f; count t>3: %d; t>4: %d" % (r.t_search.max(), (r.t_search > 3).sum(), (r.t_search > 4).sum()))
print("LUCK benchmark (10 scrambles): best t each = %s; avg count t>3 per scramble ~ %d" % (np.round(null_best, 2), (nt > 3).sum()))
top = r.sort_values("t_search", ascending=False)
print("\nTOP 30 found in 2020-24, and what they did in the locked 2025-26 period:")
print(top.head(30).round(2).to_string(index=False))
for k in [10, 50, 200, 1000]:
    tk = top.head(k); print(f"top {k:5d}: avg R search {tk.R_search.mean():+.3f} -> final {tk.R_final.mean():+.3f}; share profitable in final {(tk.R_final > 0).mean():.2f}")
print("all strategies: share profitable in final %.2f, avg R final %+.3f" % ((r.R_final > 0).mean(), r.R_final.mean()))
