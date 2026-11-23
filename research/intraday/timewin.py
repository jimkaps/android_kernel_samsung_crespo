"""Strat on NQ by time of entry. Entries any hour; exit by stop/target/bar close, flat at the end of the trading day (17:00 NY)."""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strat_bt as sb
D = sys.argv[1]
TODAY = pd.Timestamp("2026-11-23", tz="America/New_York")
daily = pd.read_pickle(f"{D}/NQ_1d.pkl"); daily = daily[daily.index < TODAY]
dd = daily.copy(); dd.index = dd.index.tz_localize(None).normalize()
wk = dd.index - pd.to_timedelta(dd.index.dayofweek, unit="D")
OPEN = pd.DataFrame({"D": dd.o, "W": dd.o.groupby(wk).transform("first"), "M": dd.o.groupby(dd.index.to_period("M")).transform("first")})
WINDOWS = [("Asia 18:00-02:00 NY (23:00-07:00 UK)", 18*60, 26*60), ("London 02:00-08:00 NY (07:00-13:00 UK)", 2*60, 8*60),
           ("US pre 08:00-09:30 NY (13:00-14:30 UK)", 8*60, 570), ("Open 09:30-10:30 NY (14:30-15:30 UK)", 570, 630),
           ("Morning 10:30-12:00 NY (15:30-17:00 UK)", 630, 720), ("Midday 12:00-14:00 NY (17:00-19:00 UK)", 720, 840),
           ("Afternoon 14:00-16:00 NY (19:00-21:00 UK)", 840, 960), ("After 16:00-17:00 NY (21:00-22:00 UK)", 960, 1020)]
def window(ts):
    mins = ts.hour * 60 + ts.minute; out = np.empty(len(ts), dtype=object)
    for name, a, z in WINDOWS:
        mm = np.where(mins < 18*60, mins + (24*60 if a >= 18*60 else 0), mins)
        out[(mm >= a) & (mm < z)] = name
    return out
def prep(m):
    sh = m.index + pd.Timedelta(hours=6); td = sh.floor("D").tz_localize(None).normalize()
    o = OPEN.reindex(td).ffill(); HO = {k: o[k].values for k in "DWM"}
    end = pd.Series(np.arange(len(m))).groupby(np.asarray(td)).transform("max").values + 1
    return HO, end
rows = []
for name, m, tfs, split in [("hourly", pd.read_pickle(f"{D}/NQ_1h.pkl").iloc[:-1], ["60min", "240min"], "2025-09-01"),
                            ("5m", pd.read_pickle(f"{D}/NQ_5m.pkl").iloc[:-1], ["5min", "15min", "30min"], "2026-10-20")]:
    HO, end = prep(m); split = pd.Timestamp(split, tz="America/New_York")
    for tf in tfs:
        b = sb.bars(m, tf)
        for setup in ["2-1-2", "2-2 rev", "3-2-2 rev"]:
            for ex in ["bar", "1R", "2R"]:
                for f in (False, True):
                    t = sb.simulate(m, b, tf, setup, ex, f, HO, end, None)
                    if not len(t): continue
                    t["win"] = window(pd.DatetimeIndex(t.time)); ins = t.time < split
                    for w, g in t.groupby("win"):
                        gi, go = g[ins[g.index]], g[~ins[g.index]]
                        rows.append(dict(data=name, tf=tf, setup=setup, exit=ex, ftfc=f, window=w, n=len(g), R=g.R.mean(),
                                         n_train=len(gi), R_train=gi.R.mean(), n_test=len(go), R_test=go.R.mean(),
                                         t=g.R.mean() / g.R.std() * np.sqrt(len(g)) if len(g) > 2 else np.nan))
r = pd.DataFrame(rows); r.to_csv(f"{D}/timewin_results.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400); pd.set_option("display.max_colwidth", 45)
for data in ["hourly", "5m"]:
    x = r[(r.data == data) & (~r.ftfc)]
    p = x.pivot_table(index=["tf", "setup", "exit"], columns="window", values="R").round(2)
    p.columns = [c.split(" ")[0] for c in p.columns]
    print(f"\n=== {data}: average R per trade by entry window (no continuity filter)"); print(p.to_string())
    ok = r[(r.data == data) & (r.n_train >= (25 if data == "hourly" else 10)) & (r.n_test >= (20 if data == "hourly" else 8)) & (r.R_train > .1) & (r.R_test > .1)]
    print(f"\n{data}: cells positive (>+0.10R) in both halves: {len(ok)} of {len(r[r.data == data])}")
    print(ok.sort_values("t", ascending=False)[["tf", "setup", "exit", "ftfc", "window", "n_train", "R_train", "n_test", "R_test", "t"]].round(2).to_string(index=False))
