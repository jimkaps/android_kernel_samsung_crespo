"""Strat setups on NQ + one confluence filter at a time. Filters use only information known at entry.
Daily TF: 2000-2026 (train <2014, test >=2014). 1h/4h TF: Jul 2024-Nov 2026 (train <Sep 2025, test >=Sep 2025)."""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strat_bt as sb
D = sys.argv[1]
TODAY = pd.Timestamp("2026-11-23", tz="America/New_York")
daily = pd.read_pickle(f"{D}/NQ_1d.pkl"); daily = daily[daily.index < TODAY]
hourly = pd.read_pickle(f"{D}/NQ_1h.pkl").iloc[:-1]

def rsi2(c):
    ch = c.diff(); up = ch.clip(lower=0).ewm(alpha=.5).mean(); dn = (-ch.clip(upper=0)).ewm(alpha=.5).mean()
    return 100 - 100 / (1 + up / dn)

def tf_feats(b):
    c = b.c; rng = b.h - b.l
    atr = rng.rolling(14).mean()
    f = pd.DataFrame(index=b.index)
    f["sma200"] = c.rolling(200).mean(); f["ema50"] = c.ewm(span=50).mean(); f["c"] = c
    f["rsi2"] = rsi2(c); f["ibs"] = (c - b.l) / rng.replace(0, np.nan)
    f["rng_atr"] = rng / atr
    vol = atr / c; f["hivol"] = vol > vol.rolling(250, min_periods=50).median()
    return f.reset_index(drop=True)

# previous completed trading day context (for intraday timeframes)
dd = daily.copy(); dd.index = dd.index.tz_localize(None).normalize()
dctx = pd.DataFrame({"pdh": dd.h, "pdl": dd.l, "pdc": dd.c, "pdo": dd.o,
                     "pd_ibs": (dd.c - dd.l) / (dd.h - dd.l), "pd_rsi2": rsi2(dd.c),
                     "d_sma200": dd.c.rolling(200).mean()}).shift(1)

def trading_date(ts):
    return (ts + pd.Timedelta(hours=6)).floor("D").tz_localize(None).normalize()

def add_filters(t, b, tf, m):
    f = tf_feats(b).iloc[t.bar.values].reset_index(drop=True)
    s = t.side.values; e = t.entry.values
    F = {}
    F["trend: with 200-bar SMA"] = s * (f.c - f.sma200).values > 0
    F["trend: with 50-bar EMA"] = s * (f.c - f.ema50).values > 0
    F["signal bar stretched (RSI2<20 long / >80 short)"] = np.where(s == 1, f.rsi2 < 20, f.rsi2 > 80)
    F["signal bar closed weak (IBS<0.3 long / >0.7 short)"] = np.where(s == 1, f.ibs < .3, f.ibs > .7)
    F["small trigger bar (<0.7 ATR)"] = (f.rng_atr < .7).values
    F["big trigger bar (>1.2 ATR)"] = (f.rng_atr > 1.2).values
    F["high-volatility regime"] = f.hivol.values.astype(bool)
    F["long trades only"] = s == 1
    F["short trades only"] = s == -1
    td = trading_date(pd.DatetimeIndex(t.time))
    x = dctx.reindex(td).reset_index(drop=True)
    if tf != "D":
        F["daily trend: with 200-day SMA"] = s * (x.pdc - x.d_sma200).values > 0
        F["yesterday closed weak/strong vs trade (IBS)"] = np.where(s == 1, x.pd_ibs < .3, x.pd_ibs > .7)
        F["yesterday RSI2 stretched vs trade"] = np.where(s == 1, x.pd_rsi2 < 20, x.pd_rsi2 > 80)
        F["entry beyond yesterday's high/low"] = np.where(s == 1, e > x.pdh, e < x.pdl)
        F["entry inside yesterday's range"] = (e < x.pdh.values) & (e > x.pdl.values)
        F["yesterday's candle same direction"] = s * (x.pdc - x.pdo).values > 0
        hr = pd.DatetimeIndex(t.time).hour
        F["entry 09:30-11:30 NY"] = (hr >= 9) & (hr < 12) if tf == "60min" else None
        F["entry after 11:30 NY"] = (hr >= 12) if tf == "60min" else None
    else:
        wk = dd.c.groupby(dd.index - pd.to_timedelta(dd.index.dayofweek, unit="D")).agg(["first", "last"])
        F["weekday not Friday entry"] = pd.DatetimeIndex(t.time).dayofweek != 4
        F["IBS-rule day for longs (dbl<.3 or <.1)"] = None
    return {k: np.asarray(v, dtype=bool) for k, v in F.items() if v is not None}

def run(m, tf, split, intraday):
    ok, end = (None, None)
    if intraday:
        mins = m.index.hour * 60 + m.index.minute; ok = (mins >= 570) & (mins < 960)
        n = len(m); s = pd.Series(np.arange(n), index=m.index); after = s[mins >= 960]
        abd = pd.Series(after.values, index=np.asarray(after.index.normalize())).groupby(level=0).min()
        end = np.maximum(pd.Series(np.asarray(m.index.normalize())).map(abd).fillna(n).astype(np.int64).values, np.arange(n) + 1)
    td = trading_date(m.index); o = (dd.o.reindex(td))
    HO = {"D": o.values, "W": o.values, "M": o.values}
    b = sb.bars(m, tf); rows = []
    for setup in ["2-1-2", "2-2 rev", "3-2-2 rev"]:
        for ex in ["bar", "2R"]:
            t = sb.simulate(m, b, tf, setup, ex, False, HO, end, ok)
            if len(t) < 40: continue
            ins = t.time < split
            def stat(mask, name):
                a, z = t.R[mask & ins], t.R[mask & ~ins]
                rows.append(dict(tf=tf, setup=setup, exit=ex, filter=name, n_train=len(a), R_train=a.mean(), n_test=len(z), R_test=z.mean(),
                                 t_all=t.R[mask].mean() / t.R[mask].std() * np.sqrt(mask.sum()) if mask.sum() > 2 else np.nan))
            stat(np.ones(len(t), bool), "(no filter)")
            for name, mask in add_filters(t, b, tf, m).items():
                stat(mask, name); stat(~mask, "NOT " + name)
    return rows

rows = run(daily, "D", pd.Timestamp("2014-01-01", tz="America/New_York"), False)
for tf in ["60min", "240min"]:
    rows += run(hourly, tf, pd.Timestamp("2025-09-01", tz="America/New_York"), tf == "60min")
r = pd.DataFrame(rows); r.to_csv(f"{D}/confluence_results.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400); pd.set_option("display.max_colwidth", 52)
base = r[r["filter"] == "(no filter)"]
print("BASE"); print(base.round(3).to_string(index=False))
good = r[(r.n_train >= 25) & (r.n_test >= 20) & (r.R_train > 0.10) & (r.R_test > 0.10)].sort_values("t_all", ascending=False)
print(f"\nFilters positive (>+0.10R) in BOTH train and test, out of {len(r) - len(base)} filter tests:")
print(good.round(3).to_string(index=False))
