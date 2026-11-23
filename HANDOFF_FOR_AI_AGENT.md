# Handoff brief: IBS trading project (for an AI agent picking this up)

You are continuing work for a UK-based retail trader (GBP account, Trading 212). This file is the full context:
what was researched, what was decided, what was built, and what's still open.
The user is not a programmer: explain in plain language, keep instructions step by step, and confirm before anything that
places real orders or spends money.

## 1. Current state in one paragraph

The user will trade an **IBS mean-reversion rule** by hand on a **Trading 212 CFD account (US Tech 100)**,
helped by a local app (`ibs_assistant/`) that alerts them at ~20:50 UK, tells them the size, logs fills and fees,
compares their real costs with the backtest, and runs a 30-day trial at £500 per trade before moving to £2,000.
Starting capital is about **£2,000**. The user wanted something low-risk and "more certain" after rejecting larger-risk versions.
They explicitly **do not want Telegram**. The app is a browser page served from their own computer.

## 2. The strategy

- **IBS** (internal bar strength) = (close − low) / (high − low) of the **US regular session** (09:30–16:00 New York), computed on **QQQ**.
- **Buy at the close** if `IBS_today < 0.30 and IBS_yesterday < 0.30` **or** `IBS_today < 0.10` **or** `RSI(2) < 10` (QQQ daily closes, Wilder smoothing alpha=0.5, today's live price as the last close).
- **Never on a Friday:** no buys on Fridays, and a held position is sold on Friday (no weekend holds).
- **Sell at the next day's close.** If the buy signal fires again that day, keep holding (no sell + rebuy).
- The RSI(2) entry and the Friday rule were added on 2026-11-17 after `research/improve.py` (see §3).
- No stop, no target. Long only (the short side had no edge).
- In practice the decision is made ~10 min before the close using the day's high/low/last at that moment (no market-on-close orders).
- Frequency: ~26 complete trades/year (buy to sell; the old "34/yr" counted HOLD nights), in the market ~10% of days, 65% winners.
- Backtest 2010–2026 at £2,000/trade after CFD costs: +£184/yr, worst DD −£235 (old rule: +£182/yr, −£365).

## 3. Research results (key numbers; scripts in `research/`)

All backtests use daily Yahoo data with costs included. "Double" = two consecutive low-IBS days.

| Version | Result | Verdict |
|---|---|---|
| Overnight double-IBS on NQ futures, 2000–2026 | strong, robust in/out of sample, also works on ES/QQQ | edge is real |
| Same on QQQ shares, $2k unleveraged, 2005–2026 | +9.7%/yr, max DD −17%, worst trade −6% | **chosen rule** |
| On LucidFlex 50K prop account, flat by the close (intraday only) | roughly break-even per £150 eval; parameter search overfitted (best 2005–16 configs lost money in 2017–26) | **rejected** |
| Own account on NQ/MNQ futures | ~$2.5–4k/yr per MNQ, worst DD ~$8k per MNQ | **rejected by user (too much risk for £2k)** |
| ES / gold micros | same % risk as NQ; one micro ≈ $38k notional = 19× leverage on $2k; gold edge not reliable (GLD lost money) | rejected |
| QQQ in a GBP Trading 212 Invest account | **0.15% FX fee each way kills it** (+9.7%/yr → −1.3%/yr) | rejected unless the account can hold USD |
| London-listed GBP ETFs (EQQQ, CNX1) | London closes 11:30 NY; IBS on that session has **no edge** (−3.3%/yr) | rejected |
| Improvements (`improve.py`): train 2001–14, test 2015–26, plus NQ/ES futures and untouched 1991–2000 index data. Kept: RSI(2)<10 as an extra entry, no Friday entries / no weekend holds. Rejected: 200-day trend filter (halves profit), VIX filters, "other index also weak", looser thresholds, alternative exits | improved rule NQ 2015–26: +£214/yr DD −£235 vs base +£203/−£285; 2001–14: +£208/−£255 vs +£135/−£298 | **adopted** |
| ES with the same rule (`es_btc.py`) | about half the NQ profit for similar risk; NQ/ES same-day returns correlate 0.83–0.90, so trading both ≈ more NQ size | NQ only |
| BTC with the same rule | loses after costs (−£129/yr, 2021+ t≈0); crypto CFDs banned for UK retail | rejected |
| **US Tech 100 CFD by hand, £2,000 per trade** | ~**+£180/yr**, max DD ~−£380, worst night ~−£126, 2 of 17 years slightly negative | **current plan** |

CFD cost assumptions used: 2-point spread round trip, manual-fill slippage 0.01%, overnight financing ~6.5%/yr on exposure
(triple on weekends), 0.5% FX on the P&L. Rolling windows at £2,000: 1 month profitable 62% of the time, 3 months 72%, 12 months 90%.

**Caveats:** Yahoo continuous futures have roll gaps. QQQ is a proxy for the CFD. Fills are assumed at the close.
IBS is a published effect and could weaken. Lucid rules came from third-party summaries with `[VERIFY]` items.

## 4. What was built

### `ibs_assistant/` (the one the user is using)
- `ibs_assistant.py`: local web app (stdlib `http.server` on `127.0.0.1:8765`) plus a scheduler thread.
  - Uses `exchange_calendars` (XNYS) to fire `MINUTES_BEFORE_CLOSE` (10) before each session close, so holidays, half-days and DST mismatches are handled.
  - Signal from Yahoo (`QQQ` daily + 1-min); index level `^NDX`; FX `GBPUSD=X`; official closes `^NDX` daily.
  - Daily job → alert BUY / SELL / HOLD / NONE, sets `pending` and fires a desktop notification (osascript / PowerShell balloon / notify-send, best effort).
  - User actions (POST JSON): `/api/filled {price}`, `/api/skip`, `/api/fee {amount}`, `/api/exposure {amount}`, `/api/check` (preview only unless ≤20 min to close), `/api/closes`.
  - Unconfirmed pending actions become "missed" at the next run.
  - Report: P&L, model P&L (same units at the official closes, no costs), real cost per trade in £ and as % of actual position size, fill slippage, missed buys.
  - Trial: after `TRIAL_DAYS` (30) and ≥3 complete trades, if cost ≤ `MAX_COST_PCT` (0.05%) → phase `full`, exposure `FULL_EXPOSURE` (£2,000); otherwise stays small.
  - Sizing: `units = exposure_gbp * GBPUSD / (index * UNIT_VALUE)`, rounded to 0.01. `UNIT_VALUE = 1.0` (USD per point per unit) was **confirmed by the user**: US Tech 100 shows ~$27,774 for 1 unit.
  - State in `assistant_state.json`, log in `assistant.log`.
- `page.html`: the single-page UI (polls `/api/state` every 20 s, browser Notification + beep on a new alert). Light/dark aware.
- `start_windows.bat`, `start_mac.command`: install deps and start.
- `raspberry_pi/install_pi.sh` + `ibs-assistant.service`: installs into a venv and runs as a systemd service with `HOST=0.0.0.0` (page reachable on the LAN, no auth). `HOST` env var defaults to 127.0.0.1. The user has a Raspberry Pi on their home network; deployment was prepared but **not yet done** (the cloud session couldn't reach it).
- `test_assistant.py`: offline tests (fake data): buy→hold→sell cycle, fees, report maths, skip, unconfirmed = missed, trial upgrade, mid-day preview. Run `python test_assistant.py`.
- `HOW_TO_USE.md`: the user's guide. `README.md`: short technical readme.

- **Exit reminders** (added after the user said they couldn't exit reliably):
  - On days a position is held, a heads-up `HEADSUP_HOURS` (3) before the close.
  - The normal SELL/HOLD at T-10, then a LAST CALL at T-`LAST_CALL_MINUTES` (4) if it's still unconfirmed.
  - The page beeps every 3 minutes while a BUY/SELL is unconfirmed, and `overdue()` shows a red banner after the close.
  - Each position stores an `exit_plan` text.
  - `research/tpsl.py`: every SL/TP combination tested was worse than exiting at the close. A 4% stop was the least bad (+£144/yr vs +£159/yr).
  - `research/exit_time.py`: exiting at the next US open gives ~+£50/yr vs +£180/yr at the close. Recommend no SL/TP.

### `android_app/` (phone version, added 2026-11-17)
Standalone Android app (Kotlin, no AndroidX): same rules, state layout and texts as `ibs_assistant.py`, ported to
`core/Engine.kt` (state = JSONObject like assistant_state.json), `core/Nyse.kt` (rule-based NYSE calendar, unit-tested
against exchange_calendars for every day 2019–2030), `core/Market.kt` (Yahoo chart API, today's H/L/last from `meta`).
Alarms: alarm-clock alarm for the decision (T−10), exact alarms for heads-up/last call/overdue only when relevant,
rescheduled on boot/update/time change. UI = `assets/index.html` in a WebView via a JS bridge. Built by GitHub Actions
(`.github/workflows/build-ibs-app.yml`) into releases tagged `ibs-app-build-N`; fixed signing key in the repo so updates install over.
The build environment for Claude sessions can't reach dl.google.com, so the Android build only runs on Actions;
`core/` tests can run locally with a plain Kotlin JVM Gradle build.

### `qqq_ibs_bot/` (alternative, not in use)
Automated QQQ-share bot for the Trading 212 **Invest/ISA** API (`/api/v0/equity/orders/market`, negative quantity = sell;
auth header = API key, or Basic base64(key:secret) for newer keys). Defaults to demo + dry run, only sells shares it bought,
and **refuses to trade live from a non-USD account** (FX fee). Endpoints came from the `trading212-rest` PyPI client because
Trading 212's docs weren't reachable from the build environment, so **verify against the official docs before live use**.
Only useful if the user's Invest/ISA account can hold USD.

### November 2026 follow-up research (see `research/FINDINGS_2026-11.md`)
- The Strat, Trader Kane's "Lab Model", ICT setups (Silver Bullet, sweeps, iFVG, midnight open, PDH/PDL raid) and fib confluence were all tested on NQ 5-minute data (2020–2026). None beat chance.
- A 70,586-strategy search with a locked 2025–26 test and a scrambled-luck benchmark found nothing. Don't re-run these hoping for a different answer.
- Improving IBS: sizing, exits, shorts, extra entries and the turn of the month didn't beat the current rule in both periods. The rule works on SPY, IWM and DIA but not on European or Asian indices. QQQ + IWM is a risk choice, not an improvement.

### `research/`
`ibs_bt.py` (core backtests), `small.py` (ES/SPY/gold/QQQ comparison), `own.py` (NQ own account), `lucid_ibs.py`, `mc.py`,
`funded.py`, `funded2.py` (prop-account sims and walk-forward), `cfd_manual.py` (the CFD P&L estimate and chart).
They expect CSVs in the working directory (`NQ_F.csv`, `QQQ.csv`, ...). Re-download with yfinance, e.g.
`yf.download('QQQ', period='max', auto_adjust=False)` and save as `QQQ.csv` (for `NQ=F` save `NQ_F.csv`).

## 5. Things the user confirmed / facts about their setup

- UK resident, thinks in £. Trading 212 (GBP account), uses the **CFD account** for this. Minimum order shown: "£20".
- US Tech 100 CFD: 1 unit = $1/point (price ~27,774 when checked). Retail CFD margin assumed 5% (1:20).
- **Still unconfirmed:** whether Trading 212's £ order box means *position value* or *margin*. The guide tells the user how to check
  (type £500 → ~0.02 units = value; ~0.47 units = margin, so type £25 instead). Follow up on this.
- Starting capital ~£2,000. Wants low risk. Not a programmer. Previously trades an NQ opening-range breakout and has
  had LucidFlex / MyFundedFutures prop accounts (separate topics).

## 6. Open items / good next steps

1. Confirm the order-box meaning (value vs margin) after the user's first trade, and that the units the app shows match.
2. After ~30 days, review `assistant_state.json` with the user: real cost per trade vs the 0.045% assumption, missed trades, slippage.
3. Optional: check whether Trading 212 Invest/ISA can hold USD. If yes, `qqq_ibs_bot` could automate it with no FX fee
   (ISA = tax-free). Otherwise IG spread betting (tax-free, has an API) is the route to full automation.
4. Optional idea not yet tested: combining this with the user's NQ opening-range strategy for more trades
   (needs the 1-minute data from an earlier `trading_research_data.zip`).
5. Don't add leverage or size until the user has 6–12 months of live results that match the backtest.

## 7. Working style the user responded well to

Clear verdict first, a small table of key numbers, honest caveats (they reacted well to "this loses money because of the FX fee").
Avoid jargon. When something can't be verified, say so plainly.
