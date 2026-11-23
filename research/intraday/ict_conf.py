"""ICT setups on NQ 5m (2020-2026) x non-ICT confluence filters. Select on 2020-23, verify on 2024-26.
Conservative fills (stop wins ties, no target in the fill bar), 1.5 pt cost, flat 16:00 NY, one trade per setup per day."""
import sys, itertools
import numpy as np, pandas as pd
F, W, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
COST, USD = 1.5, 2.0
SPLIT = pd.Timestamp("2024-01-01").date()
m = pd.read_csv(F, index_col=0)
m.index = pd.to_datetime(m.index, utc=True).tz_convert("America/New_York")
m = m.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna()
m = m[~m.index.duplicated()].sort_index()
O, H, L, C = (m[c].values for c in ["open", "high", "low", "close"])
N = len(m); mins = (m.index.hour * 60 + m.index.minute).values; date = np.array(m.index.date)
pos = {}
for i, d in enumerate(date): pos.setdefault(d, []).append(i)
alld = sorted(pos)
def idx(d, a, z): return np.array([i for i in pos.get(d, []) if a <= mins[i] < z], dtype=int)
days = [d for d in alld if len(idx(d, 570, 960)) > 60]

# ---------- daily context (all known before the day's RTH open) ----------
rth = pd.DataFrame([(d, O[idx(d, 570, 960)[0]], H[idx(d, 570, 960)].max(), L[idx(d, 570, 960)].min(), C[idx(d, 570, 960)[-1]]) for d in days],
                   columns=["d", "o", "h", "l", "c"]).set_index("d")
ctx = pd.DataFrame(index=rth.index)
pc = rth.c.shift(1)
ctx["trend"] = np.sign(pc - rth.c.rolling(20).mean().shift(1))                     # +1 above 20d SMA
ctx["ibs"] = ((rth.c - rth.l) / (rth.h - rth.l)).shift(1)
d_ = rth.c.diff(); up = d_.clip(lower=0).ewm(alpha=.5).mean(); dn = (-d_.clip(upper=0)).ewm(alpha=.5).mean()
ctx["rsi2"] = (100 - 100 / (1 + up / dn)).shift(1)
rngd = rth.h - rth.l
ctx["hivol"] = (rngd.shift(1) > rngd.rolling(20).mean().shift(1)).astype(int)
ctx["gap"] = np.sign(rth.o - pc)
ctx["pdh"], ctx["pdl"] = rth.h.shift(1), rth.l.shift(1)
vix = pd.read_csv(f"{W}/VIX.csv", index_col=0, parse_dates=True).Close; vix.index = vix.index.date
ctx["vix"] = pd.Series(ctx.index, index=ctx.index).map(lambda d: vix[vix.index < d].iloc[-1] if (vix.index < d).any() else np.nan)
nq = pd.read_csv(f"{W}/NQ_F.csv", index_col=0, parse_dates=True); es = pd.read_csv(f"{W}/ES_F.csv", index_col=0, parse_dates=True)
j = nq.join(es, lsuffix="_n", rsuffix="_e", how="inner"); j.index = j.index.date
# daily SMT on the previous completed day: NQ takes the prior low but ES doesn't (bullish) / NQ takes prior high but ES doesn't (bearish)
bull = (j.Low_n < j.Low_n.shift(1)) & (j.Low_e >= j.Low_e.shift(1)) | (j.Low_e < j.Low_e.shift(1)) & (j.Low_n >= j.Low_n.shift(1))
bear = (j.High_n > j.High_n.shift(1)) & (j.High_e <= j.High_e.shift(1)) | (j.High_e > j.High_e.shift(1)) & (j.High_n <= j.High_n.shift(1))
smt = (bull.astype(int) - bear.astype(int))
rs5 = (j.Close_n.pct_change(5) - j.Close_e.pct_change(5))
def prev(series, d):
    s = series[series.index < d]; return s.iloc[-1] if len(s) else np.nan
ctx["smt"] = [prev(smt, d) for d in ctx.index]
ctx["rs5"] = [np.sign(prev(rs5, d)) for d in ctx.index]

# ---------- trade engine ----------
def run(e, s, entry, stop, tgt, end, fill_bar=True):
    """fill_bar=True: limit/stop filled inside bar e (stop checked in e, no target in e). False: entered at close of e-1."""
    if (L[e] <= stop) if s == 1 else (H[e] >= stop):
        return (stop if fill_bar else (min(O[e], stop) if s == 1 else max(O[e], stop))), "stop"
    if not fill_bar and tgt is not None and ((H[e] >= tgt) if s == 1 else (L[e] <= tgt)): return tgt, "target"
    for j_ in range(e + 1, end):
        if (L[j_] <= stop) if s == 1 else (H[j_] >= stop): return (min(O[j_], stop) if s == 1 else max(O[j_], stop)), "stop"
        if tgt is not None and ((H[j_] >= tgt) if s == 1 else (L[j_] <= tgt)): return tgt, "target"
    return C[end - 1], "time"

def tgt_of(rule, s, entry, risk):
    return None if rule == "eod" else entry + s * risk * float(rule[0])

def trade(d, s, e, entry, stop, rule, fill_bar):
    risk = (entry - stop) * s
    if risk <= 2: return None
    end = idx(d, 570, 960)[-1] + 1
    if e >= end: return None
    px, why = run(e, s, entry, stop, tgt_of(rule, s, entry, risk), end, fill_bar)
    pts = (px - entry) * s - COST
    return dict(date=d, side=s, entry=entry, risk=risk, pts=pts, R=pts / risk, why=why, t=mins[e])

def fvgs(a, z):
    """3-bar FVGs completed at bar i in [a, z): (i, side, bottom, top, candle1 extreme)."""
    out = []
    for i in range(max(a, 2), z):
        if L[i] > H[i - 2] and L[i] - H[i - 2] >= 3: out.append((i, 1, H[i - 2], L[i], L[i - 2]))
        if H[i] < L[i - 2] and L[i - 2] - H[i] >= 3: out.append((i, -1, H[i], L[i - 2], H[i - 2]))
    return out

def silver_bullet(d, rule):
    w = idx(d, 600, 660)
    if len(w) < 3: return None
    for i, s, bot, top, c1 in fvgs(w[0], w[-1] + 1):
        ce = (bot + top) / 2; stop = c1 - 1 if s == 1 else c1 + 1
        rest = idx(d, mins[i] + 5, 660)                       # entry must fill by 11:00
        hit = [j_ for j_ in rest if (L[j_] <= ce if s == 1 else H[j_] >= ce)]
        if not hit: continue
        e = hit[0]; entry = min(O[e], ce) if s == 1 else max(O[e], ce)
        return trade(d, s, e, entry, stop, rule, True)
    return None

def sweep_ifvg(d, rule, rs, ws=600, we=780, look=12):
    r = rs(d)
    if r is None or len(r) < 3: return None
    rh, rl = H[r].max(), L[r].min(); w = idx(d, ws, we)
    swept = {1: None, -1: None}; ext = {1: np.inf, -1: -np.inf}
    for j_ in w:
        if L[j_] < rl and swept[1] is None: swept[1] = j_
        if H[j_] > rh and swept[-1] is None: swept[-1] = j_
        if swept[1] is not None: ext[1] = min(ext[1], L[j_])
        if swept[-1] is not None: ext[-1] = max(ext[-1], H[j_])
        for s in (1, -1):
            if swept[s] is None: continue
            for i, fs, bot, top, _ in fvgs(max(j_ - look, w[0]), j_):
                if fs == -s and ((s == 1 and C[j_] > top and C[j_ - 1] <= top) or (s == -1 and C[j_] < bot and C[j_ - 1] >= bot)):
                    return trade(d, s, j_ + 1, C[j_], ext[s] - s, rule, False)
    return None

def midnight_reclaim(d, rule):
    mo = idx(d, 0, 5)
    if not len(mo): return None
    mop = O[mo[0]]; w = idx(d, 570, 690); seen = {1: False, -1: False}; ext = {1: np.inf, -1: -np.inf}
    for j_ in w:
        if L[j_] < mop: seen[1] = True
        if H[j_] > mop: seen[-1] = True
        ext[1] = min(ext[1], L[j_]); ext[-1] = max(ext[-1], H[j_])
        if j_ == w[0]: continue
        if seen[1] and C[j_] > mop and C[j_ - 1] <= mop: return trade(d, 1, j_ + 1, C[j_], ext[1] - 1, rule, False)
        if seen[-1] and C[j_] < mop and C[j_ - 1] >= mop: return trade(d, -1, j_ + 1, C[j_], ext[-1] + 1, rule, False)
    return None

def pdh_pdl_raid(d, rule):
    pdh, pdl = ctx.at[d, "pdh"], ctx.at[d, "pdl"]
    if np.isnan(pdh): return None
    w = idx(d, 570, 720); took = {1: False, -1: False}; ext = {1: np.inf, -1: -np.inf}
    for j_ in w:
        if L[j_] < pdl: took[1] = True; ext[1] = min(ext[1], L[j_])
        if H[j_] > pdh: took[-1] = True; ext[-1] = max(ext[-1], H[j_])
        if took[1] and C[j_] > pdl and C[j_ - 1] <= pdl: return trade(d, 1, j_ + 1, C[j_], ext[1] - 1, rule, False)
        if took[-1] and C[j_] < pdh and C[j_ - 1] >= pdh: return trade(d, -1, j_ + 1, C[j_], ext[-1] + 1, rule, False)
    return None

SETUPS = {
    "SilverBullet 10-11": silver_bullet,
    "Sweep4h+iFVG 10-13": lambda d, r: sweep_ifvg(d, r, lambda d: idx(d, 360, 600)),
    "SweepON+iFVG 9:30-13": lambda d, r: sweep_ifvg(d, r, lambda d: np.concatenate([idx(alld[alld.index(d) - 1], 1080, 1440) if alld.index(d) else np.array([], int), idx(d, 0, 570)]), ws=570),
    "MidnightOpen reclaim": midnight_reclaim,
    "PDH/PDL raid": pdh_pdl_raid,
}
FILTERS = {
    "none": lambda t: np.ones(len(t), bool),
    "with 20d trend": lambda t: t.side == t.trend,
    "against 20d trend": lambda t: t.side == -t.trend,
    "IBS agrees (low->long)": lambda t: ((t.side == 1) & (t.ibs < .3)) | ((t.side == -1) & (t.ibs > .7)),
    "RSI2 agrees": lambda t: ((t.side == 1) & (t.rsi2 < 30)) | ((t.side == -1) & (t.rsi2 > 70)),
    "high vol day": lambda t: t.hivol == 1,
    "low vol day": lambda t: t.hivol == 0,
    "VIX>20": lambda t: t.vix > 20,
    "VIX<20": lambda t: t.vix <= 20,
    "with gap": lambda t: t.side == t.gap,
    "fade gap": lambda t: t.side == -t.gap,
    "daily SMT agrees": lambda t: t.side == t.smt,
    "NQ>ES 5d strength agrees": lambda t: t.side == t.rs5,
    "longs only": lambda t: t.side == 1,
    "shorts only": lambda t: t.side == -1,
}
import os
trades = pd.read_pickle(f"{OUT}/ict_trades.pkl") if os.path.exists(f"{OUT}/ict_trades.pkl") else {}
for nm, fn in (SETUPS.items() if not trades else []):
    for rule in ["1R", "2R", "eod"]:
        rows = [x for d in days[21:] if (x := fn(d, rule))]
        t = pd.DataFrame(rows).join(ctx, on="date"); trades[(nm, rule)] = t
    print("done", nm, len(t), flush=True)
pd.to_pickle(trades, f"{OUT}/ict_trades.pkl")
yrs_tr = (SPLIT - days[21]).days / 365.25; yrs_te = (days[-1] - SPLIT).days / 365.25
def tstat(x): return x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 and x.std() > 0 else np.nan
res = []
fl = list(FILTERS)
combos = [(a,) for a in fl] + [(a, b) for a, b in itertools.combinations(fl[1:], 2)]
for (nm, rule), t in trades.items():
    for cb in combos:
        g = np.ones(len(t), bool)
        for c in cb: g &= np.asarray(FILTERS[c](t), bool)
        x = t[g]; a, b = x[x.date < SPLIT], x[x.date >= SPLIT]
        if len(a) < 40 or len(b) < 20: continue
        res.append(dict(setup=nm, exit=rule, filters=" + ".join(cb), n_tr=len(a), R_tr=a.R.mean(), t_tr=tstat(a.R),
                        n_te=len(b), R_te=b.R.mean(), t_te=tstat(b.R), usd_yr_te=b.pts.sum() * USD / yrs_te,
                        win=(x.pts > 0).mean(), usd_yr=x.pts.sum() * USD / (yrs_tr + yrs_te)))
r = pd.DataFrame(res); r.to_csv(f"{OUT}/ict_conf_results.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200); pd.set_option("display.max_colwidth", 60)
print("tests:", len(r))
print("\nBASE setups (no filter):"); print(r[r.filters == "none"].round(3).to_string(index=False))
print("\nTop 25 by TRAIN t-stat, with their TEST result:"); print(r.sort_values("t_tr", ascending=False).head(25).round(3).to_string(index=False))
sel = r[r.t_tr > 2]
print(f"\nTrain t>2: {len(sel)} of {len(r)};  of those, test R>0: {(sel.R_te > 0).sum()}, test t>2: {(sel.t_te > 2).sum()}")
print(f"Overall share with test R>0: {(r.R_te > 0).mean():.2f}")
