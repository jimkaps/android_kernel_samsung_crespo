# IBS Assistant (US 100 CFD, traded by hand)

A small app that runs on your own computer and tells you when to buy and sell. It also keeps your trade log,
checks your real costs, runs the trial and shows how you're doing compared with the backtest.
Nothing goes through Telegram or any other service. The only thing it connects to is Yahoo Finance for prices.

## Start it

1. Install Python 3.10 or newer from python.org (on Windows, tick **"Add Python to PATH"**).
2. Unzip this folder somewhere permanent, e.g. Documents.
3. Double-click **start_windows.bat** (Windows) or **start_mac.command** (Mac; the first time,
   right-click → Open). It installs what it needs and opens **http://localhost:8765** in your browser.
4. On the page, click **Enable alerts**. Keep that tab and the black window open.

Your computer must be awake around **20:50 UK time** on US trading days. Set it not to sleep in the
evening. The time moves to 19:50 for a few weeks in March and Oct/Nov when the UK and US change clocks
on different dates, and it's earlier on US half-days. The app handles all of that.

## Every trading day

About 10 minutes before the US close the app checks the signal. If there's something to do, you get a
pop-up and a sound, and the page shows one of:

| Shows | You do in Trading 212 (CFD account, **US 100**) | Then on the page |
|---|---|---|
| **BUY** | open a **long** position of the units shown, with no stop and no target | type your fill price → **I did it** |
| **SELL** | close the whole position | type your fill price → **I did it** |
| **HOLD** | nothing; keep it open one more day | nothing |
| Nothing today | nothing | nothing |

It never says BUY on a Friday, and on Fridays a held position is always SELL (no weekend holds).

If you couldn't trade, click **I skipped it**. Missed trades are counted so you can see what they cost.
When Trading 212 charges an overnight fee, enter it under **Add overnight fee** (it's attached to the open trade).

## The trial (automatic)

- It starts at **£500 per trade**.
- After 30 days and at least 3 trades, it compares your real fills and fees with the official closes.
- If your real cost is **≤ 0.05% per trade** (the backtest assumed ~0.045%), it moves you to **£2,000 per trade**.
  If it's higher, it stays small and tells you why.
- You can change the size at any time with **Change size**.

Don't judge it on the first few weeks' P&L: one month is profitable only ~62% of the time even when the strategy
works. **Your real cost per trade** is the number to watch.

## Settings (optional, set before starting)

| Variable | Default | Meaning |
|---|---|---|
| `UNIT_VALUE` | 1.0 | USD per index point for 1 unit of the US 100 CFD. **Check this in Trading 212's instrument details** and change it if one unit is different. It sets the number of units shown. |
| `TRIAL_EXPOSURE` / `FULL_EXPOSURE` | 500 / 2000 | £ per trade in the trial / afterwards |
| `TRIAL_DAYS` | 30 | length of the trial |
| `MINUTES_BEFORE_CLOSE` | 10 | when the daily check runs |
| `PORT` | 8765 | page address |

## Notes

- **Check signal now** shows a preview during the day. Real BUY/SELL decisions are only made in the last
  20 minutes before the US close, when the day's range is nearly complete.
- Data: QQQ for the signal, ^NDX for the index level and official closes, GBPUSD for sizing (Yahoo Finance, free;
  if Yahoo fails the app retries a few times and logs the error on the page).
- Your history is in `assistant_state.json`. Back it up if you move computers.
- `python test_assistant.py` runs the offline tests.
- Past results don't guarantee future ones. Trade only money you can afford to lose.
