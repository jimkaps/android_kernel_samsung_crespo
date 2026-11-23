"""The Strat on NQ (Nasdaq-100, Dukascopy 1-minute bid candles), all timeframes, fills simulated on 1-minute data."""
import glob, os, struct, sys
import numpy as np, pandas as pd

RAW = sys.argv[1] if len(sys.argv) > 1 else "nq1m/raw"
COST_PTS = 1.5          # round trip: ~0.6 pt commission (MNQ $1.24) + spread/slippage on stop entry and stop exit
USD_PT = 2.0            # MNQ
SPLIT = pd.Timestamp("2024-01-01", tz="America/New_York")

def load_1m(raw):
    cache = os.path.join(os.path.dirname(raw.rstrip("/")), "nq_1m.pkl")
    files = sorted(glob.glob(f"{raw}/*.bin"))
    if os.path.exists(cache) and os.path.getmtime(cache) > max(os.path.getmtime(f) for f in files):
        return pd.read_pickle(cache)
    parts = []
    dt = np.dtype([("t", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("v", ">f4")])
    for f in files:
        b = open(f, "rb").read()
        if not b: continue
        a = np.frombuffer(b, dtype=dt)
        a = a[a["v"] > 0]
        if not len(a): continue
        day = pd.Timestamp(os.path.basename(f)[:10], tz="UTC")
        parts.append(pd.DataFrame({"o": a["o"] / 1000, "h": a["h"] / 1000, "l": a["l"] / 1000, "c": a["c"] / 1000},
                                  index=day + pd.to_timedelta(a["t"].astype(np.int64), unit="s")))
    d = pd.concat(parts).sort_index()
    d = d[~d.index.duplicated()]
    d.index = d.index.tz_convert("America/New_York")
    d.to_pickle(cache)
    return d

def bars(m, tf):
    """Candles on NQ's trading day (18:00-17:00 NY): shift by +6h so a trading day starts at 00:00."""
    sh = m.index + pd.Timedelta(hours=6)
    if tf in ("5min", "15min", "30min", "60min", "240min"):
        key = sh.floor(tf)
    elif tf == "D":
        key = sh.floor("D")
    elif tf == "W":
        key = (sh.floor("D") - pd.to_timedelta(sh.dayofweek, unit="D"))
    elif tf == "M":
        key = sh.floor("D") - pd.to_timedelta(sh.day - 1, unit="D")
    g = m.groupby(key)
    b = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()})
    idx = pd.Series(np.arange(len(m)), index=m.index).groupby(key)
    b["i0"] = idx.min().values; b["i1"] = idx.max().values + 1     # 1-minute index range [i0, i1)
    return b

def types(b):
    H, L = b.h.values, b.l.values
    t = np.full(len(b), "", dtype=object)
    up = H[1:] > H[:-1]; dn = L[1:] < L[:-1]
    t[1:] = np.where(up & dn, "3", np.where(up, "2u", np.where(dn, "2d", "1")))
    return t

def htf_open_arrays(m):
    """For each 1-minute bar: open of its trading day, week and month (for timeframe continuity)."""
    out = {}
    for tf in ("D", "W", "M"):
        b = bars(m, tf)
        o = np.empty(len(m))
        for op, i0, i1 in zip(b.o.values, b.i0.values, b.i1.values): o[i0:i1] = op
        out[tf] = o
    return out

def simulate(m, b, tf, setup, exit_rule, ftfc, HO, day_end, entry_ok=None):
    O, H, L, C = m.o.values, m.h.values, m.l.values, m.c.values
    T = types(b); BH, BL = b.h.values, b.l.values; I0, I1 = b.i0.values, b.i1.values
    htfs = {"5min": "DWM", "15min": "DWM", "30min": "DWM", "60min": "DWM", "240min": "DWM", "D": "WM", "W": "M", "M": ""}[tf]
    maxbars = {"bar": 1, "1R": 5, "2R": 5}[exit_rule]
    trades = []; busy_until = -1
    for i in range(2, len(b) - 1):
        if I0[i + 1] < busy_until: continue
        t1, t0 = T[i], T[i - 1]
        if setup == "2-1-2": ok = t1 == "1" and t0 in ("2u", "2d"); sides = (1, -1)
        elif setup == "3-1-2": ok = t1 == "1" and t0 == "3"; sides = (1, -1)
        elif setup == "2-2 rev": ok = t1 in ("2u", "2d"); sides = (1,) if t1 == "2d" else (-1,)
        elif setup == "3-2-2 rev": ok = t1 in ("2u", "2d") and t0 == "3"; sides = (1,) if t1 == "2d" else (-1,)
        else: raise ValueError(setup)
        if not ok: continue
        trig = {1: BH[i], -1: BL[i]}; stop = {1: BL[i], -1: BH[i]}
        a, z = I0[i + 1], I1[i + 1]
        if z - a < 1: continue
        hits = {}
        for s in sides:
            x = (H[a:z] > trig[s]) if s == 1 else (L[a:z] < trig[s])
            if x.any(): hits[s] = a + int(np.argmax(x))
        if not hits: continue
        # both sides broke in the same bar: the first side's stop is the other trigger, so it's a loss (handled by the entry-bar stop check)
        amb = len(hits) == 2 and hits[1] == hits[-1]
        if amb:   # both triggers inside one bar: assume the one nearer the bar's open broke first (then it's stopped by the other)
            k = hits[1]; s = 1 if abs(trig[1] - O[k]) <= abs(O[k] - trig[-1]) else -1
        else:
            s = min(hits, key=hits.get); k = hits[s]
        if entry_ok is not None and not entry_ok[k]: continue
        entry = max(O[k], trig[s]) if s == 1 else min(O[k], trig[s])  # stop order: gap fills at the open
        risk = (entry - stop[s]) * s
        if risk <= 0.5: continue
        if ftfc:
            if any((entry - HO[h][k]) * s <= 0 for h in htfs): continue
        tgt = None if exit_rule == "bar" else entry + s * risk * (1 if exit_rule == "1R" else 2)
        end = I1[min(i + maxbars, len(b) - 1)]
        if day_end is not None: end = min(end, day_end[k])
        if end <= k: end = k + 1
        # entry minute: assume the worst (stop first) if the stop is inside that minute's range
        if (L[k] <= stop[s]) if s == 1 else (H[k] >= stop[s]):
            px = stop[s]; j = k; why = "stop"
        else:
            hs = (L[k + 1:end] <= stop[s]) if s == 1 else (H[k + 1:end] >= stop[s])
            js = k + 1 + int(np.argmax(hs)) if hs.any() else None
            jt = None
            if tgt is not None:
                ht = (H[k:end] >= tgt) if s == 1 else (L[k:end] <= tgt)
                jt = k + int(np.argmax(ht)) if ht.any() else None
            if js is not None and (jt is None or js <= jt):
                j = js; px = min(O[j], stop[s]) if s == 1 else max(O[j], stop[s]); why = "stop"
            elif jt is not None:
                j = jt; px = tgt; why = "target"
            else:
                j = end - 1; px = C[j]; why = "time"
        pts = (px - entry) * s - COST_PTS
        trades.append((m.index[k], s, entry, px, risk, pts, pts / risk, why, i, k, amb))
        busy_until = j + 1
    return pd.DataFrame(trades, columns=["time", "side", "entry", "exit", "risk", "pts", "R", "why", "bar", "k", "amb"])

def summarize(t, years_is, years_oos):
    if len(t) < 20: return None
    ins, oos = t[t.time < SPLIT], t[t.time >= SPLIT]
    eq = t.pts.cumsum(); dd = (eq - eq.cummax()).min()
    tstat = lambda x: x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 and x.std() > 0 else np.nan
    return dict(trades=len(t), per_yr=len(t) / (years_is + years_oos), win=(t.pts > 0).mean(),
                avgR=t.R.mean(), usd_yr=t.pts.sum() * USD_PT / (years_is + years_oos), maxdd_usd=dd * USD_PT,
                R_is=ins.R.mean() if len(ins) else np.nan, R_oos=oos.R.mean() if len(oos) else np.nan,
                t_is=tstat(ins.R), t_oos=tstat(oos.R),
                usd_yr_oos=oos.pts.sum() * USD_PT / years_oos if years_oos else np.nan)

if __name__ == "__main__":
    m = load_1m(RAW)
    print("1m bars:", len(m), m.index[0], m.index[-1], flush=True)
    HO = htf_open_arrays(m)
    sh = m.index + pd.Timedelta(hours=6)
    dkey = sh.floor("D")
    pos = pd.Series(np.arange(len(m))).groupby(np.asarray(dkey)).transform("max").values + 1
    years_is = (SPLIT - m.index[0]).days / 365.25; years_oos = (m.index[-1] - SPLIT).days / 365.25
    rows = []
    for tf in ["5min", "15min", "30min", "60min", "240min", "D", "W", "M"]:
        b = bars(m, tf)
        day_end = pos if tf in ("5min", "15min", "30min", "60min", "240min") else None
        for setup in ["2-1-2", "3-1-2", "2-2 rev", "3-2-2 rev"]:
            for ex in ["bar", "1R", "2R"]:
                for f in (False, True):
                    t = simulate(m, b, tf, setup, ex, f, HO, day_end)
                    s = summarize(t, years_is, years_oos)
                    if s: rows.append(dict(tf=tf, setup=setup, exit=ex, ftfc=f, **s))
        print("done", tf, len(b), "bars", flush=True)
    r = pd.DataFrame(rows)
    r.to_csv(os.path.join(os.path.dirname(RAW.rstrip("/")), "strat_results.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    print(r.round(3).to_string(index=False))
