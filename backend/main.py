import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from ai_engine import generate_signals
from data_fetcher import fetch_market_data, get_angel_session

app = FastAPI(title="AI Trading Signal API v2 — 5TF Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory paper-trade store (session-scoped) ─────────────────────────────
_paper_trades: List[dict] = []
_trade_counter: int = 0

# ─────────────────────────────────────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "Trading API v2 is live.", "endpoints": [
        "/api/signal", "/api/candles", "/api/oi",
        "/api/paper-trade (POST/GET)", "/api/paper-trade/{id}/close (PUT)",
        "/api/paper-trade/{id} (DELETE)"
    ]}

@app.get("/api/health")
def health():
    return {"status": "ok", "time": int(time.time())}

# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/signal")
def get_signal(ticker: str = "^NSEI"):
    try:
        data = generate_signals(ticker)
        return data
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# CANDLES  — supports 5m, 15m, 30m, 1h intervals
# ─────────────────────────────────────────────────────────────────────────────
PERIOD_MAP = {
    "5m":  "2d",
    "15m": "5d",
    "30m": "30d",
    "1h":  "60d",
}

@app.get("/api/candles")
def get_candles(ticker: str = "^NSEI", interval: str = "15m"):
    period = PERIOD_MAP.get(interval, "5d")
    try:
        df = fetch_market_data(ticker, interval=interval, period=period)
        if df.empty:
            return {"candles": [], "interval": interval}
        candles = []
        for idx, row in df.iterrows():
            candles.append({
                "time":   int(idx.timestamp()),
                "open":   round(float(row["Open"]),  2),
                "high":   round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row.get("Volume", 0)),
            })
        return {"candles": candles, "interval": interval}
    except Exception as e:
        return {"candles": [], "interval": interval, "error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# OPEN INTEREST
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/oi")
def get_oi(ticker: str = "^NSEI"):
    from data_fetcher import fetch_advanced_oi
    angel = get_angel_session()
    if not angel:
        return {"oi_data": [], "pcr": None, "error": "Angel One not connected."}
    df = fetch_market_data(ticker, interval="15m", period="5d")
    if df.empty:
        return {"oi_data": [], "pcr": None}
    current_price = float(df["Close"].iloc[-1])
    try:
        oi = fetch_advanced_oi(ticker, current_price)
        return oi if oi else {"oi_data": [], "pcr": None}
    except Exception as e:
        return {"oi_data": [], "pcr": None, "error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# PAPER TRADING  (server-side store; frontend also uses localStorage)
# ─────────────────────────────────────────────────────────────────────────────
class PaperTradeIn(BaseModel):
    ticker:       str
    action:       str          # BUY or SELL
    option_type:  str          # CE or PE
    strike:       int
    entry_price:  float
    lots:         int   = 1
    lot_size:     int   = 75
    note:         Optional[str] = None

@app.post("/api/paper-trade")
def create_paper_trade(trade: PaperTradeIn):
    global _trade_counter
    _trade_counter += 1
    record = {
        "id":           _trade_counter,
        "ticker":       trade.ticker,
        "action":       trade.action,
        "option_type":  trade.option_type,
        "strike":       trade.strike,
        "entry_price":  trade.entry_price,
        "lots":         trade.lots,
        "lot_size":     trade.lot_size,
        "note":         trade.note or "",
        "timestamp":    int(time.time()),
        "status":       "open",
        "exit_price":   None,
        "pnl":          None,
    }
    _paper_trades.append(record)
    return {"success": True, "trade": record}

@app.get("/api/paper-trades")
def list_paper_trades(status: Optional[str] = None):
    if status:
        return {"trades": [t for t in _paper_trades if t["status"] == status]}
    return {"trades": _paper_trades}

@app.put("/api/paper-trade/{trade_id}/close")
def close_paper_trade(trade_id: int, exit_price: float):
    for t in _paper_trades:
        if t["id"] == trade_id and t["status"] == "open":
            t["status"]     = "closed"
            t["exit_price"] = exit_price
            ls, lots, entry = t["lot_size"], t["lots"], t["entry_price"]
            t["pnl"] = round(
                (exit_price - entry) * ls * lots if t["action"] == "BUY"
                else (entry - exit_price) * ls * lots, 2
            )
            t["close_time"] = int(time.time())
            return {"success": True, "trade": t}
    raise HTTPException(404, "Trade not found or already closed")

@app.delete("/api/paper-trade/{trade_id}")
def delete_paper_trade(trade_id: int):
    global _paper_trades
    before = len(_paper_trades)
    _paper_trades = [t for t in _paper_trades if t["id"] != trade_id]
    return {"success": len(_paper_trades) < before}
