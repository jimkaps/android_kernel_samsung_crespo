# QQQ IBS bot for Trading 212

Buys QQQ just before the US close when it closed weak, and sells it at the next close.

**Rule:** buy if today's IBS < 0.30 and yesterday's IBS < 0.30, or if today's IBS < 0.10.
Sell at the next close, but keep holding if the buy signal fires again.
IBS = (close − low) / (high − low) of the regular US session.

## Read this first: currency fees

If your Trading 212 account is in **GBP**, every QQQ buy and sell is converted GBP↔USD with a fee
of about **0.15% each way** (check the current fee on Trading 212's pricing page).
That is 0.3% per round trip, which is **more than the strategy's average profit per trade (~0.28%)**.
Backtest 2005–2026, $2k, QQQ:

| Cost per round trip | Per year | Worst drawdown |
|---|---|---|
| none (USD account) | +9.7% | −17% |
| 0.15% | +4.0% | −24% |
| 0.30% (GBP account, 0.15% each way) | **−1.3%** | −43% |

So the bot **refuses to trade live from a non-USD account** unless you set `ALLOW_FX=1`.
To trade without the fee, you need cash held in USD: check whether your Trading 212 account can
hold a USD balance, or use a broker with a USD cash balance (for example Interactive Brokers).

## Setup

1. Install Python 3.10+ and the libraries:

   ```bash
   pip install requests pandas yfinance exchange_calendars
   ```

2. In the Trading 212 app: Settings → API (Beta) → generate a key. Give it permissions for
   **account data, portfolio, orders read and orders execute**. Do this on the **Practice**
   account first. If you're given a key and a secret, keep both.

3. Set the environment variables (example for macOS/Linux; on Windows use `setx` or a `.bat` file):

   ```bash
   export T212_API_KEY="your key"
   export T212_API_SECRET="your secret, if you got one"
   export T212_ENV=demo       # demo = Practice account, live = real money
   export DRY_RUN=1           # 1 = only log what it would do
   ```

## Running

| Command | What it does |
|---|---|
| `python qqq_ibs_bot.py --signal` | prints today's IBS and whether it's a buy (no login needed) |
| `python qqq_ibs_bot.py --status` | shows account currency, cash, QQQ position and bot state |
| `python qqq_ibs_bot.py` | runs forever and trades 6 minutes before each US close (handles holidays and half-days) |
| `python qqq_ibs_bot.py --once` | one decision now; for a scheduled task at 15:54 New York time |
| `python test_bot.py` | offline tests with a fake broker |

The US close is 21:00 UK time most of the year, and 20:00 UK for a few weeks in March and in
October/November when the clocks change on different dates. The built-in scheduler handles this.
A computer or small server has to be on at that time. A cheap VPS or a Raspberry Pi works well.

**Going live, in order:** run on `demo` with `DRY_RUN=1` for a few days → `demo` with `DRY_RUN=0`
for a couple of weeks, checking that orders fill → `live` with `DRY_RUN=1` → `live` with `DRY_RUN=0`.

## Safety features

- Defaults to the Practice account and dry run.
- Only sells the shares it bought itself (tracked in `state.json`). QQQ you hold by hand is never touched.
- Uses at most `CASH_FRACTION` (97%) of free cash and at most `MAX_ORDER_VALUE` (2500) per buy.
- Only trades in the last 20 minutes before the close. Retries if rate-limited. Logs everything to `bot.log`.
- Won't trade live from a non-USD account (see above).

## Limits

- It buys a few minutes **before** the close, using the IBS at that moment. Trading 212 has no
  market-on-close order. Some days the signal will flip in the last minutes, and fills differ a little from the backtest.
- Price data comes from Yahoo Finance (free, can occasionally fail). If it fails, the bot logs an error and skips that day.
- Trading 212's API is in beta. I couldn't reach their documentation from where this was written.
  The endpoints match a published Trading 212 client library, so **test on Practice first**:
  `/api/v0/equity/orders/market` with `{"ticker":"QQQ_US_EQ","quantity":±qty}`, where a negative quantity sells.
- Past results don't guarantee future ones. The strategy lost money in 4 of 22 backtest years.
