"""The Strat on Nasdaq-100 5-minute bars 2020-2026 (user-supplied HistData file). Train 2020-2023, test 2024-2026."""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strat_bt as sb
F, OUT = sys.argv[1], sys.argv[2]
m = pd.read_csv(F, index_col=0)
m.index = pd.to_datetime(m.index, utc=True).tz_convert("America/New_York")
m = m.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c"})[["o", "h", "l", "c"]].dropna()
m = m[(m.h >= m.l)]; m = m[~m.index.duplicated()].sort_index()
print("bars", len(m), m.index[0], m.index[-1], flush=True)
sb.SPLIT = pd.Timestamp("2024-01-01", tz="America/New_York")
HO = sb.htf_open_arrays(m)
mins = m.index.hour * 60 + m.index.minute
rth_ok = (mins >= 570) & (mins < 960)
n = len(m); s = pd.Series(np.arange(n), index=m.index); after = s[mins >= 960]
abd = pd.Series(after.values, index=np.asarray(after.index.normalize())).groupby(level=0).min()
rth_end = np.maximum(pd.Series(np.asarray(m.index.normalize())).map(abd).fillna(n).astype(np.int64).values, np.arange(n) + 1)
td = (m.index + pd.Timedelta(hours=6)).floor("D")
day_end = pd.Series(np.arange(n)).groupby(np.asarray(td)).transform("max").values + 1
WIN = [("Asia", 18*60, 26*60), ("London", 120, 480), ("USpre", 480, 570), ("Open", 570, 630), ("Morning", 630, 720),
       ("Midday", 720, 840), ("Afternoon", 840, 960), ("After", 960, 1020)]
def window(ts):
    mm = ts.hour * 60 + ts.minute; mm = np.where(mm < 120, mm + 1440, mm); out = np.full(len(ts), "", dtype=object)
    for nm, a, z in WIN:
        a2, z2 = (a, z) if a >= 120 else (a + 1440, z + 1440)
        out[(mm >= a2) & (mm < z2)] = nm
    return out
yi = (sb.SPLIT - m.index[0]).days / 365.25; yo = (m.index[-1] - sb.SPLIT).days / 365.25
rows, wrows, keep = [], [], {}
for tf in ["5min", "15min", "30min", "60min", "240min"]:
    b = sb.bars(m, tf); intraday = tf != "240min"
    for setup in ["2-1-2", "3-1-2", "2-2 rev", "3-2-2 rev"]:
        for ex in ["bar", "1R", "2R"]:
            for f in (False, True):
                # main grid: US-session entries for <=1h (flat by 16:00); 4h any hour, flat by 17:00
                t = sb.simulate(m, b, tf, setup, ex, f, HO, rth_end if intraday else day_end, rth_ok if intraday else None)
                sm = sb.summarize(t, yi, yo) if len(t) >= 20 else None
                rows.append(dict(tf=tf, setup=setup, exit=ex, ftfc=f, **(sm or {"trades": len(t)})))
                keep[(tf, setup, ex, f)] = t
                # time windows: entries any hour, flat by 17:00
                ta = sb.simulate(m, b, tf, setup, ex, f, HO, day_end, None)
                if len(ta):
                    ta["win"] = window(pd.DatetimeIndex(ta.time)); ins = (ta.time < sb.SPLIT).values
                    for w in ta.win.unique():
                        g = ta.win.values == w
                        a_, z_ = ta.R[g & ins], ta.R[g & ~ins]
                        wrows.append(dict(tf=tf, setup=setup, exit=ex, ftfc=f, window=w, n_train=len(a_), R_train=a_.mean(),
                                          n_test=len(z_), R_test=z_.mean(), n=g.sum(), R=ta.R[g].mean(),
                                          t=ta.R[g].mean() / ta.R[g].std() * np.sqrt(g.sum()) if g.sum() > 2 else np.nan))
    print("done", tf, len(b), flush=True)
r = pd.DataFrame(rows); w = pd.DataFrame(wrows)
r.to_csv(f"{OUT}/strat_long_results.csv", index=False); w.to_csv(f"{OUT}/strat_long_windows.csv", index=False)
pd.to_pickle(keep, f"{OUT}/strat_long_trades.pkl")
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
print(r[r.trades >= 20][["tf", "setup", "exit", "ftfc", "trades", "per_yr", "win", "avgR", "R_is", "R_oos", "t_is", "t_oos", "usd_yr", "maxdd_usd"]].round(2).to_string(index=False))
