"""Mechanical approximation of 'Trader Kane / Lab Model' ideas on NQ 5m (2020-2026).
Model A 'rebalance': take a reference range; trade its 50% level in the direction of the range candle.
Model B 'sweep+iFVG': price sweeps the reference range high/low, then closes through a recent opposite FVG -> reversal entry.
Conservative 5m fills: stop wins any bar where stop and target both trade; no target in the fill bar; flat by 16:00 NY."""
import sys, itertools
import numpy as np, pandas as pd
F, OUT = sys.argv[1], sys.argv[2]
COST, USD = 1.5, 2.0        # points per round trip; $ per point (MNQ)
SPLIT = pd.Timestamp("2024-01-01").date()
m = pd.read_csv(F, index_col=0)
m.index = pd.to_datetime(m.index, utc=True).tz_convert("America/New_York")
m = m.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna()
m = m[~m.index.duplicated()].sort_index()
O, H, L, C = (m[c].values for c in ["open", "high", "low", "close"])
mins = (m.index.hour * 60 + m.index.minute).values
date = np.array(m.index.date)
days = sorted(set(date[(mins >= 570) & (mins < 960)]))
pos = {}
for i, d in enumerate(date): pos.setdefault(d, []).append(i)
alld = sorted(pos)

def idx(d, a, z, prev=False):
    """bar indices on date d with a<=minute<z; prev=True also takes the previous calendar day's bars from minute a (overnight)."""
    if prev:
        k = alld.index(d); out = []
        if k > 0: out = [i for i in pos[alld[k - 1]] if mins[i] >= a]
        return np.array(out + [i for i in pos[d] if mins[i] < z], dtype=int)
    return np.array([i for i in pos[d] if a <= mins[i] < z], dtype=int)

RANGES = {  # name: (range bars spec, entry window start, entry window end)
    "4h_06-10":   (lambda d: idx(d, 360, 600), 600, 780),
    "overnight":  (lambda d: idx(d, 1080, 570, prev=True), 570, 780),
    "first_hour": (lambda d: idx(d, 570, 630), 630, 780),
    "prev_day":   (None, 570, 780),
}
def rng(name, d, k):
    if name == "prev_day":
        if k == 0: return None
        r = idx(days[k - 1], 570, 960)
    else:
        r = RANGES[name][0](d)
    return r if len(r) >= 3 else None

def manage(e, s, entry, stop, tgt, end):
    """from bar e (fill bar) to end (exclusive): returns exit price and reason."""
    if (L[e] <= stop) if s == 1 else (H[e] >= stop): return stop, "stop"
    for j in range(e + 1, end):
        if (L[j] <= stop) if s == 1 else (H[j] >= stop): return (min(O[j], stop) if s == 1 else max(O[j], stop)), "stop"
        if tgt is not None and ((H[j] >= tgt) if s == 1 else (L[j] <= tgt)): return tgt, "target"
    return C[end - 1], "time"

def model_a(rname, level, tgt_rule, filt, ws_over=None, we_over=None):
    out = []
    for k, d in enumerate(days):
        r = rng(rname, d, k)
        if r is None: continue
        rh, rl = H[r].max(), L[r].min(); ro, rc = O[r[0]], C[r[-1]]
        if rh - rl < 10: continue
        s = 1 if rc > ro else -1
        if filt == "daytrend":   # also require the previous RTH day to close in the same direction
            if k == 0: continue
            p = idx(days[k - 1], 570, 960)
            if not len(p) or np.sign(C[p[-1]] - O[p[0]]) != s: continue
        ws, we = RANGES[rname][1], RANGES[rname][2]
        if ws_over: ws, we = ws_over, we_over
        w = idx(d, ws, we); day = idx(d, ws, 960)
        if not len(w): continue
        entry_px = rl + level * (rh - rl) if s == 1 else rh - level * (rh - rl)
        stop = rl - 1 if s == 1 else rh + 1
        hit = np.where(L[w] <= entry_px)[0] if s == 1 else np.where(H[w] >= entry_px)[0]
        if not len(hit): continue
        e = w[hit[0]]
        entry = min(O[e], entry_px) if s == 1 else max(O[e], entry_px)
        risk = (entry - stop) * s
        if risk <= 2: continue
        tgt = {"1R": entry + s * risk, "2R": entry + s * 2 * risk, "range_ext": rh if s == 1 else rl, "eod": None}[tgt_rule]
        if tgt is not None and (tgt - entry) * s <= 0: tgt = None
        end = day[-1] + 1
        px, why = manage(e, s, entry, stop, tgt, end)
        pts = (px - entry) * s - COST
        out.append((d, s, entry, px, risk, pts, pts / risk, why))
    return pd.DataFrame(out, columns=["date", "side", "entry", "exit", "risk", "pts", "R", "why"])

def model_b(rname, tgt_rule, look=12):
    out = []
    for k, d in enumerate(days):
        r = rng(rname, d, k)
        if r is None: continue
        rh, rl = H[r].max(), L[r].min()
        ws, we = RANGES[rname][1], RANGES[rname][2]
        w = idx(d, ws, we); day = idx(d, ws, 960)
        if len(w) < 5: continue
        done = False; swept = {1: None, -1: None}; ext = {1: np.inf, -1: -np.inf}
        for jj, j in enumerate(w):
            if L[j] < rl and swept[1] is None: swept[1] = j
            if H[j] > rh and swept[-1] is None: swept[-1] = j
            if swept[1] is not None: ext[1] = min(ext[1], L[j])
            if swept[-1] is not None: ext[-1] = max(ext[-1], H[j])
            for s in (1, -1):
                if swept[s] is None or j - 2 < swept[s] - look: continue
                # recent FVGs against the trade direction, formed in the last `look` bars
                lo = max(j - look, w[0] + 2)
                for f in range(j - 1, lo - 1, -1):
                    if s == 1 and L[f - 2] > H[f]:      # bearish FVG: gap (H[f], L[f-2])
                        top = L[f - 2]
                        if C[j] > top and C[j - 1] <= top: break
                    elif s == -1 and H[f - 2] < L[f]:   # bullish FVG: gap (H[f-2], L[f])
                        bot = H[f - 2]
                        if C[j] < bot and C[j - 1] >= bot: break
                else:
                    continue
                entry = C[j]; stop = ext[s] - 1 if s == 1 else ext[s] + 1
                risk = (entry - stop) * s
                if risk <= 2 or j + 1 >= day[-1] + 1: continue
                tgt = {"1R": entry + s * risk, "2R": entry + s * 2 * risk, "3R": entry + s * 3 * risk,
                       "range_mid": (rh + rl) / 2, "eod": None}[tgt_rule]
                if tgt is not None and (tgt - entry) * s <= 0: continue
                # enter at the close of bar j -> manage from j+1 (treat j+1 as first bar, no entry-bar stop shortcut needed)
                e = j + 1
                if (L[e] <= stop) if s == 1 else (H[e] >= stop):
                    px, why = (min(O[e], stop) if s == 1 else max(O[e], stop)), "stop"
                else:
                    px, why = manage(e, s, entry, stop, tgt, day[-1] + 1)
                    if why == "stop" and False: pass
                    # target in bar e itself (bar after entry is fully after the fill)
                    if tgt is not None and ((H[e] >= tgt) if s == 1 else (L[e] <= tgt)): px, why = tgt, "target"
                pts = (px - entry) * s - COST
                out.append((d, s, entry, px, risk, pts, pts / risk, why)); done = True; break
            if done: break
    return pd.DataFrame(out, columns=["date", "side", "entry", "exit", "risk", "pts", "R", "why"])

def summ(t):
    if len(t) < 20: return dict(trades=len(t))
    yrs = (days[-1] - days[0]).days / 365.25
    a, b = t[t.date < SPLIT], t[t.date >= SPLIT]
    ts = lambda x: x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 else np.nan
    eq = t.pts.cumsum(); dd = (eq - eq.cummax()).min()
    return dict(trades=len(t), per_yr=round(len(t) / yrs), win=(t.pts > 0).mean(), avgR=t.R.mean(),
                R_train=a.R.mean(), R_test=b.R.mean(), t_train=ts(a.R), t_test=ts(b.R),
                usd_yr=t.pts.sum() * USD / yrs, maxdd_usd=dd * USD)

rows = []; keep = {}
for rn, lv, tg, fl in itertools.product(RANGES, [0.5, 0.618], ["1R", "2R", "range_ext", "eod"], ["none", "daytrend"]):
    t = model_a(rn, lv, tg, fl); keep[("A", rn, lv, tg, fl)] = t
    rows.append(dict(model="A rebalance", range=rn, level=lv, target=tg, filter=fl, **summ(t)))
print("A done", flush=True)
for rn, tg in itertools.product(RANGES, ["1R", "2R", "3R", "range_mid", "eod"]):
    t = model_b(rn, tg); keep[("B", rn, tg)] = t
    rows.append(dict(model="B sweep+iFVG", range=rn, level=np.nan, target=tg, filter="none", **summ(t)))
print("B done", flush=True)
r = pd.DataFrame(rows); r.to_csv(f"{OUT}/kane_results.csv", index=False); pd.to_pickle(keep, f"{OUT}/kane_trades.pkl")
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
print(r.round(2).to_string(index=False))
