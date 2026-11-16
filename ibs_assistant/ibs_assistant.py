#!/usr/bin/env python3
"""
IBS trading assistant: a small app on your own computer for trading the US 100 CFD by hand.

Run it, and a page opens in your browser (http://localhost:8765). Keep that tab open.
Every US trading day ~10 minutes before the close (20:50 UK most of the year) it checks the signal and,
if there is something to do, pops up a notification with a sound:
  BUY  -> open a long US 100 position of the size shown
  SELL -> close yesterday's position
  HOLD -> signal fired again, keep it open
Rule: buy if QQQ's IBS < 0.30 today and yesterday, or < 0.10 today; sell at the next close.

On the page you log what you actually did (fill price, skipped, fees). It keeps the trade log,
compares your fills with the official close, works out your real cost per trade, runs the trial
(small size first, then moves you up if your costs are in line) and shows your P&L vs the model.
Everything is stored in assistant_state.json next to this file. Nothing leaves your computer
except the price downloads from Yahoo Finance.
"""
import json, logging, os, platform, subprocess, sys, threading, time, traceback, webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd
import yfinance as yf
import exchange_calendars as xcals

PORT = int(os.environ.get("PORT", "8765"))
UNIT_VALUE = float(os.environ.get("UNIT_VALUE", "1.0"))   # USD per index point for 1 unit of the CFD (check Trading 212's instrument details)
TRIAL_EXPOSURE = float(os.environ.get("TRIAL_EXPOSURE", "500"))
FULL_EXPOSURE = float(os.environ.get("FULL_EXPOSURE", "2000"))
TRIAL_DAYS = int(os.environ.get("TRIAL_DAYS", "30"))
MINUTES_BEFORE_CLOSE = int(os.environ.get("MINUTES_BEFORE_CLOSE", "10"))
MAX_COST_PCT = float(os.environ.get("MAX_COST_PCT", "0.05"))   # backtest assumed ~0.045% of exposure per trade
DBL, SINGLE = 0.30, 0.10

HERE = Path(os.environ.get("BOT_DIR", Path(__file__).resolve().parent))
STATE = HERE / "assistant_state.json"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.FileHandler(HERE / "assistant.log"), logging.StreamHandler(sys.stdout)])
log = logging.getLogger("ibs-assistant")
NYSE = xcals.get_calendar("XNYS")
LOCK = threading.RLock()


# ======================= state =======================
def new_state():
    return {"started": str(datetime.now(timezone.utc).date()), "phase": "trial", "exposure": TRIAL_EXPOSURE,
            "position": None, "pending": None, "trades": [], "events": [],
            "alert": None, "last_run": None, "trial_checked": False, "next_check": None}

def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else new_state()

def save_state(s):
    STATE.write_text(json.dumps(s, indent=2, default=str))

def event(s, kind, text, **extra):
    s["events"].insert(0, {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "kind": kind, "text": text, **extra})
    s["events"] = s["events"][:300]


# ======================= notifications =======================
def desktop_notify(title, text):
    """Best-effort pop-up outside the browser. The browser tab also shows one and plays a sound."""
    try:
        sysname = platform.system()
        if sysname == "Darwin":
            subprocess.run(["osascript", "-e", f'display notification "{text}" with title "{title}" sound name "Glass"'], timeout=10)
        elif sysname == "Windows":
            ps = ("[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null;"
                  "$n = New-Object System.Windows.Forms.NotifyIcon; $n.Icon = [System.Drawing.SystemIcons]::Information;"
                  f"$n.Visible = $true; $n.ShowBalloonTip(15000, '{title}', '{text}', 'Info'); Start-Sleep 16; $n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
        else:
            subprocess.run(["notify-send", title, text], timeout=10)
    except Exception as e:
        log.info(f"desktop notification not shown ({e}); the browser tab will still alert")


# ======================= market data =======================
def _dl(t, **kw):
    df = yf.download(t, auto_adjust=False, progress=False, **kw)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def ibs(h, l, c):
    return (c - l) / (h - l) if h > l else 0.5

def signal_now():
    daily = _dl("QQQ", period="15d", interval="1d")
    intr = _dl("QQQ", period="1d", interval="1m", prepost=False)
    if intr.empty:
        raise RuntimeError("no intraday QQQ data from Yahoo")
    today = intr.index[-1].tz_convert("America/New_York").date()
    y = daily[daily.index.date < today].iloc[-1]
    it = ibs(float(intr.High.max()), float(intr.Low.min()), float(intr.Close.iloc[-1]))
    iy = ibs(float(y.High), float(y.Low), float(y.Close))
    return dict(date=str(today), ibs_today=round(it, 3), ibs_yesterday=round(iy, 3),
                signal=bool((it < DBL and iy < DBL) or it < SINGLE))

def market_levels():
    ndx = _dl("^NDX", period="1d", interval="1m")
    fx = _dl("GBPUSD=X", period="5d", interval="1d")
    return float(ndx.Close.iloc[-1]), float(fx.Close.iloc[-1])

def official_close(date_str):
    d = _dl("^NDX", period="3mo", interval="1d")
    row = d[d.index.date == pd.Timestamp(date_str).date()]
    return float(row.Close.iloc[0]) if len(row) else None

def units_for(exposure_gbp, level, gbpusd):
    """CFD units so the position is worth ~exposure_gbp (the US 100 CFD is priced in USD)."""
    return max(0.01, round(exposure_gbp * gbpusd / (level * UNIT_VALUE), 2))


# ======================= the daily decision =======================
def minutes_to_close(now=None):
    now = now or datetime.now(timezone.utc)
    if not NYSE.is_session(now.date()):
        return None
    return (NYSE.session_close(NYSE.date_to_session(now.date())) - now).total_seconds() / 60

def daily_job(s, force=False):
    sig = signal_now()
    if force:
        m = minutes_to_close()
        if m is None or not (0 < m <= 20):
            would = "BUY-type signal so far" if sig["signal"] else "no signal so far"
            event(s, "preview", f"Preview only ({sig['date']}): IBS today {sig['ibs_today']}, yesterday {sig['ibs_yesterday']}: "
                                f"{would}. Real decisions are made in the last 10–20 min before the US close.")
            return
    if s.get("last_run") == sig["date"]:
        return
    s["last_run"] = sig["date"]
    if s.get("pending"):
        event(s, "warn", f"Previous {s['pending']['action']} was never confirmed. Logged as missed.", missed=s["pending"]["action"])
        s["pending"] = None
    level, gbpusd = market_levels()
    s["gbpusd"] = gbpusd
    info = f"IBS today {sig['ibs_today']}, yesterday {sig['ibs_yesterday']}"
    pos = s.get("position")
    if pos and sig["signal"]:
        alert = dict(action="HOLD", text=f"Signal fired again. Keep your {pos['units']} units open until tomorrow's close.")
    elif pos:
        s["pending"] = {"action": "SELL", "date": sig["date"], "units": pos["units"], "model_px": level}
        alert = dict(action="SELL", text=f"Close your US 100 position ({pos['units']} units) now. Index ≈ {level:,.1f}.")
    elif sig["signal"]:
        units = units_for(s["exposure"], level, gbpusd)
        s["pending"] = {"action": "BUY", "date": sig["date"], "units": units, "model_px": level}
        alert = dict(action="BUY", text=f"Open a long US 100 position of {units} units now "
                                        f"(≈ £{s['exposure']:,.0f}, index ≈ {level:,.1f}). No stop, no target.")
    else:
        alert = dict(action="NONE", text="Nothing to do today.")
    s["alert"] = {**alert, "date": sig["date"], "info": info, "id": f"{sig['date']}-{alert['action']}"}
    event(s, alert["action"].lower(), f"{sig['date']}: {alert['action']}. {alert['text']} ({info})")
    if alert["action"] != "NONE":
        desktop_notify(f"IBS: {alert['action']}", alert["text"])


# ======================= user actions =======================
def act_filled(s, price):
    p = s.get("pending")
    if not p:
        raise ValueError("Nothing is waiting for a fill.")
    if p["action"] == "BUY":
        s["position"] = {"entry_date": p["date"], "units": p["units"], "fill": price, "model_px": p["model_px"],
                         "fees": 0.0, "exposure": s["exposure"], "fx": s.get("gbpusd") or 1.30}
        event(s, "fill", f"Bought {p['units']} units at {price:,.1f}")
    else:
        pos = s["position"]; fx = pos.get("fx") or s.get("gbpusd") or 1.30
        pnl = (price - pos["fill"]) * pos["units"] * UNIT_VALUE / fx - pos["fees"]
        s["trades"].append({**pos, "exit_date": p["date"], "exit_fill": price, "exit_model_px": p["model_px"],
                            "pnl_gbp": round(pnl, 2)})
        s["position"] = None
        event(s, "fill", f"Sold at {price:,.1f}. Trade P&L ≈ £{pnl:+.2f}")
    s["pending"] = None
    if s.get("alert"): s["alert"]["done"] = True

def act_skip(s):
    p = s.get("pending")
    if not p:
        raise ValueError("Nothing to skip.")
    event(s, "warn", f"Skipped {p['action']} on {p['date']}", missed=p["action"])
    s["pending"] = None
    if s.get("alert"): s["alert"]["done"] = True

def act_fee(s, amount):
    if s.get("position"):
        s["position"]["fees"] += amount; where = "open position"
    elif s["trades"]:
        s["trades"][-1]["fees"] += amount; s["trades"][-1]["pnl_gbp"] = round(s["trades"][-1]["pnl_gbp"] - amount, 2); where = "last trade"
    else:
        raise ValueError("No trade to attach the fee to.")
    event(s, "fee", f"£{amount:.2f} fee added to {where}")


# ======================= reporting & trial =======================
def fill_closes(s):
    for t in s["trades"]:
        try:
            t["close_entry"] = t.get("close_entry") or official_close(t["entry_date"])
            t["close_exit"] = t.get("close_exit") or official_close(t["exit_date"])
        except Exception:
            pass

def report(s):
    tr = s["trades"]
    missed = sum(1 for e in s["events"] if e.get("missed") == "BUY")
    out = dict(n=len(tr), wins=sum(t["pnl_gbp"] > 0 for t in tr), pnl=round(sum(t["pnl_gbp"] for t in tr), 2),
               fees=round(sum(t["fees"] for t in tr), 2), missed=missed, model=None, cost_per=None, cost_pct=None, slip=None)
    full = [t for t in tr if t.get("close_entry") and t.get("close_exit")]
    if full:
        gbp_pt = lambda t: t["units"] * UNIT_VALUE / (t.get("fx") or 1.30)           # £ per index point for this trade
        model = [(t["close_exit"] - t["close_entry"]) * gbp_pt(t) for t in full]      # same units, exactly at the closes, no costs
        real = [t["pnl_gbp"] for t in full]
        slip = [((t["fill"] - t["close_entry"]) - (t["exit_fill"] - t["close_exit"])) * gbp_pt(t) for t in full]
        size = sum(t["close_entry"] * gbp_pt(t) for t in full) / len(full)           # actual £ size of the position
        cost = (sum(model) - sum(real)) / len(full)
        out.update(model=round(sum(model), 2), cost_per=round(cost, 2),
                   cost_pct=round(cost / size * 100, 3), slip=round(sum(slip) / len(slip), 2))
    return out

def trial_check(s):
    if s["phase"] != "trial" or s.get("trial_checked"):
        return
    if (datetime.now(timezone.utc).date() - pd.Timestamp(s["started"]).date()).days < TRIAL_DAYS:
        return
    fill_closes(s); r = report(s)
    if r["cost_pct"] is None or r["n"] < 3:
        event(s, "info", "Trial: fewer than 3 complete trades. Keeping the small size, will check again.")
        return
    s["trial_checked"] = True
    if r["cost_pct"] <= MAX_COST_PCT:
        s["phase"] = "full"; s["exposure"] = FULL_EXPOSURE
        msg = (f"Trial passed: your real cost is {r['cost_pct']}% per trade, in line with the backtest. "
               f"Moving to £{FULL_EXPOSURE:,.0f} per trade from the next signal.")
    else:
        msg = (f"Trial: your real cost is {r['cost_pct']}% per trade, above the {MAX_COST_PCT}% the strategy can afford. "
               "Staying small. Check the spread/overnight fee and place orders closer to the close.")
    event(s, "trial", msg); desktop_notify("IBS trial result", msg)


# ======================= scheduler thread =======================
def next_fire(after):
    sess = NYSE.date_to_session(after.date(), direction="next")
    fire = NYSE.session_close(sess) - timedelta(minutes=MINUTES_BEFORE_CLOSE)
    if fire < after:
        fire = NYSE.session_close(NYSE.next_session(sess)) - timedelta(minutes=MINUTES_BEFORE_CLOSE)
    return fire

def scheduler():
    fire = next_fire(datetime.now(timezone.utc))
    with LOCK:
        s = load_state(); s["next_check"] = fire.isoformat(); save_state(s)
    while True:
        now = datetime.now(timezone.utc)
        if now >= fire:
            for attempt in range(5):
                try:
                    with LOCK:
                        s = load_state(); daily_job(s); trial_check(s); save_state(s)
                    break
                except Exception:
                    log.error(traceback.format_exc()); time.sleep(30)
            fire = next_fire(datetime.now(timezone.utc) + timedelta(minutes=MINUTES_BEFORE_CLOSE + 1))
            with LOCK:
                s = load_state(); s["next_check"] = fire.isoformat(); save_state(s)
        time.sleep(15)


# ======================= web page =======================
PAGE = (HERE / "page.html") if (HERE / "page.html").exists() else Path(__file__).with_name("page.html")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, obj, code=200):
        b = json.dumps(obj, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            b = PAGE.read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(b)
        elif self.path == "/api/state":
            with LOCK:
                s = load_state(); self._json({"state": s, "report": report(s), "config": {"trial_days": TRIAL_DAYS, "full": FULL_EXPOSURE}})
        else:
            self.send_error(404)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        try:
            with LOCK:
                s = load_state()
                if self.path == "/api/filled":   act_filled(s, float(body["price"]))
                elif self.path == "/api/skip":   act_skip(s)
                elif self.path == "/api/fee":    act_fee(s, abs(float(body["amount"])))
                elif self.path == "/api/exposure":
                    s["exposure"] = float(body["amount"]); event(s, "info", f"Exposure set to £{s['exposure']:,.0f}")
                elif self.path == "/api/check":  daily_job(s, force=True)
                elif self.path == "/api/closes": fill_closes(s)
                else: return self.send_error(404)
                save_state(s)
            self._json({"ok": True})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 400)

def main():
    if not STATE.exists():
        save_state(new_state())
    threading.Thread(target=scheduler, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)        # only reachable from this computer
    url = f"http://localhost:{PORT}"
    log.info(f"IBS assistant running at {url} (Ctrl+C to stop)")
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    srv.serve_forever()

if __name__ == "__main__":
    main()
