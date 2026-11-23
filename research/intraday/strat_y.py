"""The Strat on NQ futures using Yahoo data: D/W/M on daily bars 2000-2026, 1h/4h on hourly bars, 5m-30m on 5-minute bars."""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strat_bt as sb

D = sys.argv[1]
TODAY = pd.Timestamp("2026-11-23", tz="America/New_York")
daily = pd.read_pickle(f"{D}/NQ_1d.pkl"); daily = daily[daily.index < TODAY]

def trading_date(idx):
    return (idx + pd.Timedelta(hours=6)).floor("D").tz_localize(None).normalize()

# higher-timeframe opens per trading date, from the daily series
dd = daily.copy(); dd.index = dd.index.tz_localize(None).normalize()
wk = dd.index - pd.to_timedelta(dd.index.dayofweek, unit="D"); mo = dd.index.to_period("M")
OPEN = pd.DataFrame({"D": dd.o, "W": dd.o.groupby(wk).transform("first"), "M": dd.o.groupby(mo).transform("first")})

def htf(m):
    td = trading_date(m.index)
    o = OPEN.reindex(td).ffill()
    return {k: o[k].values for k in "DWM"}

def rth(m):
    t = m.index; mins = t.hour * 60 + t.minute
    ok = (mins >= 570) & (mins < 960)
    td = np.asarray(t.normalize())
    end = np.empty(len(m), dtype=np.int64); n = len(m)
    s = pd.Series(np.arange(n), index=t)
    after = s[mins >= 960]
    after_by_day = pd.Series(after.values, index=np.asarray(after.index.normalize())).groupby(level=0).min()
    nxt = pd.Series(td).map(after_by_day).fillna(n).astype(np.int64).values
    return ok, np.maximum(nxt, np.arange(n) + 1)

def yrs(m):
    return (m.index[-1] - m.index[0]).days / 365.25

SPLITS = {"daily": pd.Timestamp("2014-01-01", tz="America/New_York"),
          "hourly": pd.Timestamp("2025-09-01", tz="America/New_York"),
          "5m": pd.Timestamp("2026-10-20", tz="America/New_York")}
plans = [("daily", daily, ["D", "W", "M"]),
         ("hourly", pd.read_pickle(f"{D}/NQ_1h.pkl").iloc[:-1], ["60min", "240min"]),
         ("5m", pd.read_pickle(f"{D}/NQ_5m.pkl").iloc[:-1], ["5min", "15min", "30min"])]
rows = []; trades_all = {}
for name, m, tfs in plans:
    sb.SPLIT = SPLITS[name]
    HO = htf(m)
    ok, end_rth = rth(m)
    y_is = (sb.SPLIT - m.index[0]).days / 365.25; y_oos = (m.index[-1] - sb.SPLIT).days / 365.25
    for tf in tfs:
        b = sb.bars(m, tf)
        intraday = tf in ("5min", "15min", "30min", "60min")
        for setup in ["2-1-2", "3-1-2", "2-2 rev", "3-2-2 rev"]:
            for ex in ["bar", "1R", "2R"]:
                for f in (False, True):
                    t = sb.simulate(m, b, tf, setup, ex, f, HO, end_rth if intraday else None, ok if intraday else None)
                    trades_all[(tf, setup, ex, f)] = t
                    s = sb.summarize(t, y_is, y_oos) if len(t) >= 20 else None
                    if s: rows.append(dict(data=name, tf=tf, setup=setup, exit=ex, ftfc=f, **s))
                    else: rows.append(dict(data=name, tf=tf, setup=setup, exit=ex, ftfc=f, trades=len(t)))
        print("done", tf, len(b), "bars", m.index[0].date(), "->", m.index[-1].date(), flush=True)
r = pd.DataFrame(rows); r.to_csv(f"{D}/strat_results.csv", index=False)
pd.to_pickle(trades_all, f"{D}/strat_trades.pkl")
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 500)
print(r.round(3).to_string(index=False))
