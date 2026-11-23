import numpy as np, pandas as pd
EXPO, RT, FIN, FX = 2000.0, 0.0002, 0.065 / 365, 0.005
TODAY = pd.Timestamp("2026-11-23")
def load(f):
    d = pd.read_csv(f, index_col=0, parse_dates=True)[["Open", "High", "Low", "Close"]].dropna(); d = d[d.High > d.Low]
    return d[d.index < TODAY]
def feats(d):
    d = d.copy(); d["ibs"] = (d.Close - d.Low) / (d.High - d.Low); d["ibs1"] = d.ibs.shift(1)
    ch = d.Close.diff(); up = ch.clip(lower=0).ewm(alpha=.5).mean(); dn = (-ch.clip(upper=0)).ewm(alpha=.5).mean(); d["rsi2"] = 100 - 100 / (1 + up / dn)
    d["sma200"] = d.Close.rolling(200).mean(); d["vol20"] = d.Close.pct_change().rolling(20).std()
    d["volmed"] = d.vol20.expanding(250).median(); d["dow"] = d.index.dayofweek
    d["nxt_dow"] = pd.Series(d.index, index=d.index).shift(-1).dt.dayofweek
    return d.dropna(subset=["sma200", "volmed"])
def sig_cur(d):
    raw = ((d.ibs < .3) & (d.ibs1 < .3)) | (d.ibs < .1) | (d.rsi2 < 10)
    return raw & (d.dow != 4)
def run(d, sig, side=1, size=None, exit_open=False):
    """enter at close on signal; exit next close (or next open); hold while signal repeats (close exits only); never hold over a weekend."""
    S = sig.values; C = d.Close.values; Op = d.Open.values; idx = d.index; out = []; i = 0; n = len(d)
    sz = np.ones(n) if size is None else size
    while i < n - 1:
        if not S[i]: i += 1; continue
        j = i + 1
        if not exit_open:
            while j < n - 1 and S[j]: j += 1
        px = Op[j] if exit_open else C[j]
        r = (px / C[i] - 1) * side; e = EXPO * sz[i]; nights = (idx[j] - idx[i]).days
        g = r * e - abs(r * e) * FX - e * RT - e * FIN * nights
        out.append((idx[i], idx[j], r, g, sz[i])); i = j if exit_open else j + 1
    return pd.DataFrame(out, columns=["date", "exit", "r", "gbp", "size"])
def st(t, a, b):
    t = t[(t.date >= a) & (t.date < b)]; yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    if len(t) < 10: return dict(tr_yr=len(t) / yrs)
    daily = t.groupby("exit").gbp.sum(); e = daily.cumsum(); dd = (e - e.cummax()).min(); py = t.gbp.sum() / yrs
    return dict(tr_yr=len(t) / yrs, gbp_yr=py, dd=dd, win=(t.gbp > 0).mean(), t=t.gbp.mean() / t.gbp.std() * np.sqrt(len(t)), score=py / -dd * 1000 if dd < 0 else np.nan, avg_size=t["size"].mean())
SPLITS = [("2001-01-01", "2015-01-01"), ("2015-01-01", "2026-11-23")]
def row(name, t):
    a, b = (st(t, *s) for s in SPLITS)
    return {"variant": name, **{f"{k}_tr": v for k, v in a.items()}, **{f"{k}_te": v for k, v in b.items()}}
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 100)
cols = ["variant", "tr_yr_tr", "gbp_yr_tr", "dd_tr", "t_tr", "score_tr", "tr_yr_te", "gbp_yr_te", "dd_te", "t_te", "score_te", "win_te", "avg_size_te"]
q = feats(load("work/QQQ.csv"))
S0 = sig_cur(q); rows = []
rows.append(row("0 CURRENT RULE", run(q, S0)))
volsz = np.clip((q.volmed / q.vol20).values, 0.5, 2.0)
rows.append(row("S1 size by volatility (0.5x-2x)", run(q, S0, size=volsz)))
strong = (((q.ibs < .1) & (q.rsi2 < 10)) | (q.rsi2 < 5)).values
rows.append(row("S2 1.5x when very oversold", run(q, S0, size=np.where(strong, 1.5, 1.0))))
rows.append(row("S3 1.5x when below 200d avg", run(q, S0, size=np.where(q.Close < q.sma200, 1.5, 1.0))))
rows.append(row("S4 2x when VIX-like vol high (vol20>med)", run(q, S0, size=np.where(q.vol20 > q.volmed, 2.0, 1.0))))
rows.append(row("X1 exit next OPEN (overnight only)", run(q, S0, exit_open=True)))
rows.append(row("X2 allow Friday entries (hold weekend)", run(q, ((q.ibs < .3) & (q.ibs1 < .3)) | (q.ibs < .1) | (q.rsi2 < 10))))
sh = (q.ibs > .9) & (q.rsi2 > 90) & (q.Close < q.sma200) & (q.dow != 4)
rows.append(row("SH short IBS>.9 & RSI2>90 below 200d", run(q, sh, side=-1)))
sh2 = (q.ibs > .9) & (q.rsi2 > 95) & (q.dow != 4)
rows.append(row("SH2 short IBS>.9 & RSI2>95 any trend", run(q, sh2, side=-1)))
lowbb = q.Close < q.Close.rolling(20).mean() - 2 * q.Close.rolling(20).std()
rows.append(row("E1 + close below lower Bollinger band", run(q, S0 | (lowbb & (q.dow != 4)))))
dn3 = (q.Close.diff() < 0) & (q.Close.diff().shift(1) < 0) & (q.Close.diff().shift(2) < 0)
rows.append(row("E2 + 3 down closes in a row", run(q, S0 | (dn3 & (q.dow != 4)))))
mo = q.index.to_period("M"); last = pd.Series(mo, index=q.index) != pd.Series(mo, index=q.index).shift(-1)
rows.append(row("T  turn-of-month alone (buy last day, 1 day)", run(q, last & (q.dow != 4))))
rows.append(row("E3 + turn-of-month", run(q, S0 | (last & (q.dow != 4)))))
print("=== QQQ (Nasdaq-100), £2,000/trade, Trading 212 CFD costs.  TRAIN 2001-2014 | TEST 2015-2026  (score = £/yr per £1,000 worst drawdown)")
print(pd.DataFrame(rows)[cols].round(2).to_string(index=False))
# ---- other markets with the same rule
mk = {"QQQ (US100)": "work/QQQ.csv", "SPY (US500)": "work/SPY.csv", "DIA (US30)": "idx/DIA.csv", "IWM (US2000)": "idx/IWM.csv", "DAX (DE40)": "idx/DAX.csv",
      "FTSE (UK100)": "idx/FTSE.csv", "Euro Stoxx 50": "idx/SX5E.csv", "Nikkei (JP225)": "idx/N225.csv", "Hang Seng": "idx/HSI.csv", "Gold": "idx/GOLD.csv"}
T = {}; rows = []
for nm, f in mk.items():
    d = feats(load(f)); t = run(d, sig_cur(d)); T[nm] = t; rows.append(row(nm, t))
print("\n=== Same rule on other markets")
print(pd.DataFrame(rows)[cols[:-1]].round(2).to_string(index=False))
pnl = pd.DataFrame({k: v.groupby("exit").gbp.sum() for k, v in T.items()}).fillna(0)
pnl = pnl[pnl.index >= "2008-01-01"]
print("\nCorrelation of daily P&L (2008+), with QQQ:"); print(pnl.corr()["QQQ (US100)"].round(2).to_string())
pd.to_pickle(T, "idx/market_trades.pkl")
