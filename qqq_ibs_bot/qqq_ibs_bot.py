#!/usr/bin/env python3
"""
QQQ IBS bot for Trading 212.

Strategy (the one we backtested):
  IBS = (close - low) / (high - low) of the regular-session day.
  BUY at the close if  (today IBS < 0.30 and yesterday IBS < 0.30)  or  today IBS < 0.10.
  SELL at the next day's close. If the buy signal fires again that day, keep holding.
  Trades are placed a few minutes before the close (Trading 212 has no market-on-close orders),
  using the day's high/low/last price at that moment.

Safety defaults: demo account and dry run. Nothing is sent to a real account until you set
T212_ENV=live and DRY_RUN=0 yourself.

The bot only sells shares it bought itself (tracked in state.json), so QQQ you hold
by hand is left alone.
"""
import argparse, base64, json, logging, math, os, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf
import exchange_calendars as xcals

# ---------------- configuration (environment variables) ----------------
API_KEY      = os.environ.get("T212_API_KEY", "")
API_SECRET   = os.environ.get("T212_API_SECRET", "")          # newer keys come with a secret; leave empty for old-style keys
ENV          = os.environ.get("T212_ENV", "demo").lower()      # demo | live
DRY_RUN      = os.environ.get("DRY_RUN", "1") != "0"           # 1 = log what it would do, send nothing
TICKER_T212  = os.environ.get("T212_TICKER", "QQQ_US_EQ")
TICKER_DATA  = os.environ.get("DATA_TICKER", "QQQ")
CASH_FRAC    = float(os.environ.get("CASH_FRACTION", "0.97"))  # share of free cash to use per buy (leave room for FX fee / price move)
MAX_ORDER    = float(os.environ.get("MAX_ORDER_VALUE", "2500"))# hard cap per buy, in account currency
QTY_DECIMALS = int(os.environ.get("QTY_DECIMALS", "3"))        # fractional share precision
ALLOW_FX     = os.environ.get("ALLOW_FX", "0") == "1"           # trade even if the account is not in USD (currency fee eats the edge!)
MINUTES_BEFORE_CLOSE = int(os.environ.get("MINUTES_BEFORE_CLOSE", "6"))
DBL, SINGLE  = 0.30, 0.10

HERE  = Path(os.environ.get("BOT_DIR", Path(__file__).resolve().parent))
STATE = HERE / "state.json"
LOG   = HERE / "bot.log"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.FileHandler(LOG), logging.StreamHandler(sys.stdout)])
log = logging.getLogger("qqq-ibs")
NYSE = xcals.get_calendar("XNYS")


# ---------------- Trading 212 client ----------------
class T212:
    def __init__(self, key, secret, env):
        if not key:
            raise SystemExit("Set T212_API_KEY (and T212_API_SECRET if your key has one).")
        self.base = f"https://{'live' if env == 'live' else 'demo'}.trading212.com/api/v0"
        if secret:
            token = base64.b64encode(f"{key}:{secret}".encode()).decode()
            self.headers = {"Authorization": f"Basic {token}"}
        else:
            self.headers = {"Authorization": key}
        self.s = requests.Session()

    def _req(self, method, path, **kw):
        for attempt in range(4):
            r = self.s.request(method, self.base + path, headers=self.headers, timeout=20, **kw)
            if r.status_code == 429:                        # rate limited: back off and retry
                time.sleep(2 + 3 * attempt); continue
            if r.status_code >= 400:
                raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
            return r.json() if r.text else None
        raise RuntimeError(f"{method} {path}: still rate-limited after retries")

    def cash(self):               return self._req("GET", "/equity/account/cash")
    def info(self):               return self._req("GET", "/equity/account/info")
    def portfolio(self):          return self._req("GET", "/equity/portfolio")
    def order(self, oid):         return self._req("GET", f"/equity/orders/{oid}")
    def market_order(self, ticker, qty):   # positive qty = buy, negative = sell
        return self._req("POST", "/equity/orders/market", json={"ticker": ticker, "quantity": qty})

    def position_qty(self, ticker):
        for p in self.portfolio() or []:
            if p.get("ticker") == ticker:
                return float(p.get("quantity", 0))
        return 0.0

    def wait_filled(self, oid, timeout=90):
        end = time.time() + timeout; last = None
        while time.time() < end:
            try:
                o = self.order(oid); last = o.get("status")
            except RuntimeError as e:
                if "404" in str(e):        # filled orders drop off the open-orders list
                    return "FILLED_OR_GONE"
                raise
            if last in ("FILLED", "CANCELLED", "REJECTED"):
                return last
            time.sleep(3)
        return last or "UNKNOWN"


# ---------------- state ----------------
def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"bot_qty": 0.0, "entry_date": None, "entry_price": None, "history": []}

def save_state(st):
    STATE.write_text(json.dumps(st, indent=2, default=str))


# ---------------- market data & signal ----------------
def ibs(h, l, c):
    return (c - l) / (h - l) if h > l else 0.5

def todays_signal():
    """IBS for today (using the session's high/low/last so far) and yesterday (completed bar)."""
    daily = yf.download(TICKER_DATA, period="15d", interval="1d", auto_adjust=False, progress=False)
    intr  = yf.download(TICKER_DATA, period="1d", interval="1m", auto_adjust=False, prepost=False, progress=False)
    for df in (daily, intr):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    if intr.empty:
        raise RuntimeError("no intraday data for today (holiday or data problem)")
    today = intr.index[-1].tz_convert("America/New_York").date()
    hist = daily[daily.index.date < today]                  # completed days only
    y = hist.iloc[-1]
    ibs_y = ibs(y.High, y.Low, y.Close)
    h, l, c = float(intr.High.max()), float(intr.Low.min()), float(intr.Close.iloc[-1])
    ibs_t = ibs(h, l, c)
    sig = (ibs_t < DBL and ibs_y < DBL) or ibs_t < SINGLE
    info = dict(date=str(today), high=round(h, 2), low=round(l, 2), last=round(c, 2),
                ibs_today=round(ibs_t, 3), ibs_yesterday=round(ibs_y, 3), signal=bool(sig))
    return sig, c, info


# ---------------- one decision (run near the close) ----------------
def run_once(force=False):
    now = datetime.now(timezone.utc)
    session = NYSE.date_to_session(now.date(), direction="none") if NYSE.is_session(now.date()) else None
    if session is None and not force:
        log.info("market closed today - nothing to do"); return
    close = NYSE.session_close(session) if session is not None else now
    mins_left = (close - now).total_seconds() / 60
    if not force and not (0.5 < mins_left <= 20):
        log.info(f"{mins_left:.0f} min to the close - only trades in the last 20 min (use --force to override)"); return

    sig, px, info = todays_signal()
    log.info(f"signal check {info}")
    st = load_state()
    mode = f"{ENV.upper()}{' DRY-RUN' if DRY_RUN else ''}"
    api = T212(API_KEY, API_SECRET, ENV)

    ccy = (api.info() or {}).get("currencyCode", "?")
    if ccy != "USD" and not DRY_RUN and not ALLOW_FX:
        log.error(f"account currency is {ccy}, not USD: each QQQ trade would pay a currency conversion fee "
                  "(~0.15% each way), which is more than the strategy's average profit. Not trading. "
                  "Set ALLOW_FX=1 to trade anyway."); return
    held_by_bot = float(st["bot_qty"])
    if held_by_bot > 0:
        actual = api.position_qty(TICKER_T212)
        if actual + 1e-9 < held_by_bot:
            log.warning(f"state says bot holds {held_by_bot} but account has {actual}; using {actual}")
            held_by_bot = actual
        if sig:
            log.info(f"[{mode}] holding {held_by_bot} and buy signal fired again -> keep holding")
            st["history"].append({**info, "action": "hold"}); save_state(st); return
        log.info(f"[{mode}] SELL {held_by_bot} {TICKER_T212} (~{px:.2f})")
        if not DRY_RUN:
            o = api.market_order(TICKER_T212, -round(held_by_bot, QTY_DECIMALS))
            status = api.wait_filled(o["id"]); log.info(f"sell order {o['id']} status {status}")
        pnl = (px / st["entry_price"] - 1) * 100 if st.get("entry_price") else None
        st["history"].append({**info, "action": "sell", "qty": held_by_bot, "approx_pnl_pct": pnl})
        st.update(bot_qty=0.0, entry_date=None, entry_price=None); save_state(st)
        return

    if not sig:
        log.info(f"[{mode}] no position, no signal -> nothing to do")
        st["history"].append({**info, "action": "none"}); save_state(st); return

    cash = api.cash()
    free = float(cash.get("free", 0))
    budget = min(free * CASH_FRAC, MAX_ORDER)
    qty = math.floor(budget / px * 10 ** QTY_DECIMALS) / 10 ** QTY_DECIMALS
    if qty <= 0:
        log.warning(f"not enough free cash ({free}) to buy"); return
    log.info(f"[{mode}] BUY {qty} {TICKER_T212} (~{px:.2f}, ~{qty * px:.0f} of free {free:.0f})")
    if not DRY_RUN:
        o = api.market_order(TICKER_T212, qty)
        status = api.wait_filled(o["id"]); log.info(f"buy order {o['id']} status {status}")
        qty = api.position_qty(TICKER_T212) if status != "REJECTED" else 0.0
        if status in ("CANCELLED", "REJECTED"):
            log.error("buy did not fill"); return
    st.update(bot_qty=qty, entry_date=info["date"], entry_price=px)
    st["history"].append({**info, "action": "buy", "qty": qty}); save_state(st)


# ---------------- simple scheduler (keep it running) ----------------
def loop():
    log.info(f"bot started: env={ENV} dry_run={DRY_RUN} ticker={TICKER_T212}")
    while True:
        now = datetime.now(timezone.utc)
        sess = NYSE.date_to_session(now.date(), direction="next")
        fire = NYSE.session_close(sess) - timedelta(minutes=MINUTES_BEFORE_CLOSE)
        if fire <= now:                                     # already past today's fire time -> next session
            sess = NYSE.next_session(sess); fire = NYSE.session_close(sess) - timedelta(minutes=MINUTES_BEFORE_CLOSE)
        log.info(f"next run {fire.astimezone().strftime('%Y-%m-%d %H:%M %Z')}")
        while datetime.now(timezone.utc) < fire:
            time.sleep(min(300, max(1, (fire - datetime.now(timezone.utc)).total_seconds())))
        try:
            run_once()
        except Exception as e:
            log.exception(f"run failed: {e}")
        time.sleep(120)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run one decision now (for cron / Task Scheduler)")
    ap.add_argument("--force", action="store_true", help="with --once: ignore the time/market checks (testing)")
    ap.add_argument("--signal", action="store_true", help="only print today's IBS and signal")
    ap.add_argument("--status", action="store_true", help="show account cash, QQQ position and bot state")
    a = ap.parse_args()
    if a.signal:
        print(json.dumps(todays_signal()[2], indent=2)); return
    if a.status:
        api = T212(API_KEY, API_SECRET, ENV)
        print("account:", api.info()); print("cash:", api.cash()); print("QQQ position:", api.position_qty(TICKER_T212)); print("state:", load_state()); return
    if a.once:
        run_once(force=a.force); return
    loop()

if __name__ == "__main__":
    main()
