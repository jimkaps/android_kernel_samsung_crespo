import numpy as np, pandas as pd, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from ibs_bt import load
from small import trades
EXPO = 2000.0                        # GBP exposure per trade (not compounding)
SPREAD = 0.00010                     # ~2 index points round trip at 25,000 + a little slippage
FUND_PER_NIGHT = 0.065 / 365         # overnight fee ~6.5%/yr on the exposure (base rate + broker markup)
MANUAL = 0.00010                     # placing it by hand ~5 min before the close: small extra cost
FX_ON_PNL = 0.005                    # conversion fee on the P&L itself (assumed; check app)
d = load('QQQ.csv'); d = d[d.index >= '2010']
t = trades(d, 0.3, 'next', 0.0, 0.1)
t['exit'] = [d.index[d.index.get_loc(x) + b] for x, b in zip(t.date, t.bars)]
nights = (t.exit - t.date).dt.days
gross = t.r * EXPO
t['gbp'] = gross - np.abs(gross) * FX_ON_PNL - EXPO * (SPREAD + MANUAL) - EXPO * FUND_PER_NIGHT * nights
eq = t.set_index('exit').gbp.cumsum(); dd = eq - eq.cummax()
yrs = (eq.index[-1] - t.date.iloc[0]).days / 365.25
yr = t.groupby(t.exit.dt.year).gbp.sum()
print(f"2010-2026, £{EXPO:.0f} per trade: {len(t)/yrs:.0f} trades/yr, win {np.mean(t.gbp>0):.0%}, avg £{t.gbp.mean():+.2f}/trade")
print(f"total £{eq.iloc[-1]:,.0f} = £{eq.iloc[-1]/yrs:,.0f}/yr ({eq.iloc[-1]/yrs/EXPO*100:.1f}% of £2k)  worst DD £{dd.min():,.0f}  worst trade £{t.gbp.min():,.0f}  best trade £{t.gbp.max():,.0f}")
print("costs per trade: spread+manual £%.2f, overnight £%.2f avg" % (EXPO*(SPREAD+MANUAL), (EXPO*FUND_PER_NIGHT*nights).mean()))
print("by year:", yr.round().astype(int).to_dict())
m = t.set_index('exit').gbp.resample('ME').sum()
for months in (1, 3, 6, 12):
    roll = m.rolling(months).sum().dropna()
    print(f"any {months:2d}-month window: profitable {np.mean(roll>0):.0%} of the time, median £{roll.median():+.0f}, worst £{roll.min():+.0f}, best £{roll.max():+.0f}")
last = t[t.exit >= '2025-11-16']; print(f"last 12 months: {len(last)} trades, £{last.gbp.sum():+.0f}")
# chart
INK, INK2, GRID, BLUE, RED = '#0b0b0b', '#52514e', '#e4e3df', '#2a78d6', '#e34948'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.edgecolor':GRID,'axes.labelcolor':INK2,'xtick.color':INK2,'ytick.color':INK2,'axes.spines.top':False,'axes.spines.right':False})
fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.8), dpi=200, facecolor='#fcfcfb', sharex=True, gridspec_kw=dict(height_ratios=[2.2, 1]))
for a in (a1, a2): a.set_facecolor('#fcfcfb'); a.grid(axis='y', color=GRID, lw=.8); a.axhline(0, color=INK2, lw=.8)
a1.step(eq.index, eq.values, where='post', color=BLUE, lw=2)
a1.set_title('Manual US 100 CFD, IBS rule, £2,000 exposure per trade: cumulative P&L after costs', loc='left', color=INK, fontsize=11.5, fontweight='bold')
a1.set_ylabel('Cumulative £')
a2.fill_between(dd.index, dd.values, 0, step='post', color=RED, alpha=.35, lw=0); a2.step(dd.index, dd.values, where='post', color=RED, lw=1)
a2.set_title('Drawdown from previous high', loc='left', color=INK, fontsize=11, fontweight='bold'); a2.set_ylabel('£')
fig.text(.01, .005, 'Buy US 100 at ~20:55 UK when QQQ IBS<0.3 two days running or <0.1 today; sell at next close. Costs: 2pt spread, manual slippage, ~6.5%/yr overnight fee, 0.5% FX on P&L.', fontsize=7.5, color=INK2)
fig.tight_layout(rect=(0, .02, 1, 1)); fig.savefig('cfd_manual_pnl.png', facecolor='#fcfcfb')
