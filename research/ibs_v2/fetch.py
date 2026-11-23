import json, urllib.request, time, sys, pandas as pd
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
for sym, name in [("^GDAXI", "DAX"), ("^FTSE", "FTSE"), ("^N225", "N225"), ("^STOXX50E", "SX5E"), ("IWM", "IWM"), ("DIA", "DIA"), ("^HSI", "HSI"), ("GC=F", "GOLD"), ("^NDX", "NDXd"), ("ES=F", "ESF")]:
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=946684800&period2={int(time.time())}&interval=1d"
    try:
        j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20))["chart"]["result"][0]
        q = j["indicators"]["quote"][0]
        d = pd.DataFrame({"Open": q["open"], "High": q["high"], "Low": q["low"], "Close": q["close"]}, index=pd.to_datetime(j["timestamp"], unit="s").normalize())
        d.index.name = "Date"; d.dropna().to_csv(f"idx/{name}.csv"); print(name, len(d), d.index[0].date(), d.index[-1].date())
    except Exception as e: print(name, "ERR", e)
