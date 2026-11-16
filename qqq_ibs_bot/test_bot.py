"""Offline tests: fake broker + fake market data, checks buy / hold / sell decisions."""
import importlib, os, sys, tempfile
os.environ.update(T212_API_KEY="test", DRY_RUN="0", BOT_DIR=tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(__file__))
bot = importlib.import_module("qqq_ibs_bot")

class FakeAPI:
    def __init__(self, *a): self.orders = []
    pos = 0.0
    def cash(self): return {"free": 2000.0}
    ccy = "USD"
    def info(self): return {"currencyCode": FakeAPI.ccy}
    def position_qty(self, t): return FakeAPI.pos
    def market_order(self, t, q): self.orders.append(q); FakeAPI.pos += q; FakeAPI.last = q; return {"id": 1}
    def wait_filled(self, oid): return "FILLED"

def run(sig, px=500.0):
    bot.T212 = FakeAPI
    bot.todays_signal = lambda: (sig, px, {"date": "2026-01-02", "signal": sig})
    FakeAPI.last = None
    bot.run_once(force=True)
    return FakeAPI.last

def test_cycle():
    FakeAPI.pos = 0.0
    assert run(False) is None                       # flat, no signal
    q = run(True); assert q == 3.88                 # 2000*0.97/500 = 3.88 shares
    assert run(True) is None                        # signal again -> hold
    assert run(False) == -3.88                      # next day no signal -> sell
    assert bot.load_state()["bot_qty"] == 0

def test_manual_shares_untouched():
    FakeAPI.pos = 10.0                              # user owns 10 QQQ by hand
    bot.save_state({"bot_qty": 0.0, "entry_date": None, "entry_price": None, "history": []})
    assert run(False) is None                       # bot holds nothing -> never sells user's shares

def test_refuses_gbp_account():
    FakeAPI.pos = 0.0; FakeAPI.ccy = "GBP"
    bot.save_state({"bot_qty": 0.0, "entry_date": None, "entry_price": None, "history": []})
    assert run(True) is None                        # GBP account -> no order without ALLOW_FX=1
    FakeAPI.ccy = "USD"

def test_ibs():
    assert bot.ibs(10, 0, 2) == 0.2 and bot.ibs(5, 5, 5) == 0.5

if __name__ == "__main__":
    test_cycle(); test_manual_shares_untouched(); test_refuses_gbp_account(); test_ibs(); print("all tests passed")
