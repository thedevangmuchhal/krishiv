# 🚀 AI Trading Dashboard v2 — 5-Timeframe Signal Engine

> **Educational & Paper Trading Only.** Not SEBI-registered financial advice.

---

## What's New in v2

| Feature | v1 | v2 |
|---|---|---|
| Timeframes | 15m, 1h, 4h | **5m, 15m, 30m, 1h, 4h** |
| MTF Matrix | Text only | **Visual 5-cell colour matrix** |
| Supertrend | Bug (chained-assign) | **Fixed (numpy loop)** |
| Chart overlays | Candles only | **EMA 9/21/50 + VWAP + PDH/PDL + OI lines** |
| Chart TF tabs | None | **5m / 15m / 30m / 1h tabs** |
| Paper Trading | None | **BUY CE / BUY PE + live P&L + history** |
| Signal reasons | None | **Human-readable reasoning list** |
| Fibonacci | None | **7-level retracement from recent swing** |
| Camarilla Pivots | None | **8 levels from PDH/PDL/PDC** |
| EMA Stack | None | **9/21/50/200 alignment label** |
| Patterns | 4 patterns | **13 patterns incl. Morning/Evening Star** |
| Risk:Reward | None | **Auto-calculated ratio** |

---

## Project Structure

```
Trading_Dashboard/
├── backend/
│   ├── ai_engine.py        ← 5TF engine (UPGRADED)
│   ├── main.py             ← FastAPI + paper trade endpoints (UPGRADED)
│   ├── data_fetcher.py     ← Angel One + yfinance + NSE (unchanged)
│   ├── ml_engine.py        ← sklearn breakout predictor (unchanged)
│   ├── options_math.py     ← Black-Scholes / Greeks (unchanged)
│   ├── backtester.py       ← Backtest engine (unchanged)
│   ├── train_model.py      ← Retrain script (unchanged)
│   ├── requirements.txt    ← Dependencies (updated)
│   └── model.pkl           ← Pretrained model
└── frontend/
    └── index.html          ← Complete UI (REBUILT)
```

---

## How to Deploy

### Backend (Render)
1. Push this folder to GitHub
2. On Render → New Web Service → connect your repo
3. **Root directory**: `backend`
4. **Build command**: `pip install -r requirements.txt`
5. **Start command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add environment variables:
   ```
   ANGEL_API_KEY=your_key
   ANGEL_CLIENT_ID=your_id
   ANGEL_TOTP_SECRET=your_totp
   ANGEL_PASSWORD=your_pin
   ```

### Frontend
Just open `frontend/index.html` in any browser. No build step needed.

> Update `API_BASE` at the top of `index.html` if your Render URL changes.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/signal?ticker=^NSEI` | Full signal with all data |
| GET | `/api/candles?ticker=^NSEI&interval=15m` | Candle OHLCV for chart |
| GET | `/api/oi?ticker=^NSEI` | OI chain (requires Angel One) |
| POST | `/api/paper-trade` | Log a paper trade |
| GET | `/api/paper-trades` | List all paper trades |
| PUT | `/api/paper-trade/{id}/close?exit_price=X` | Close a trade |
| DELETE | `/api/paper-trade/{id}` | Delete a trade |

### Supported Tickers
| Ticker | Index |
|---|---|
| `^NSEI` | NIFTY 50 |
| `^NSEBANK` | BANK NIFTY |
| `NIFTY_FIN_SERVICE.NS` | FIN NIFTY |
| `^BSESN` | SENSEX |

### Supported Chart Intervals
`5m` · `15m` · `30m` · `1h`

---

## Signal Logic — 5TF Confluence

```
Score = avg(Smart Money, Options Flow, Technical, Sentiment)

Smart Money:   FII + DII net flows from NSE
Options Flow:  PCR, VPCR, Max Pain, IV Skew, OI Buildup
Technical:     5TF MTF + EMA Stack + Supertrend + RSI Div
               + StochRSI + Volume Surge + ORB + Patterns
               + PDH/PDL Breakout + BB + VWAP Cross + ML
Sentiment:     VADER NLP on Google News + VIX % change
```

### 5TF Confluence Bonus/Penalty
| Alignment | Score Delta |
|---|---|
| 5/5 Bullish | +30 |
| 4/5 Bullish | +20 |
| 3/5 Bullish | +10 |
| 3/5 Bearish | -10 |
| 4/5 Bearish | -20 |
| 5/5 Bearish | -30 |

### Action Thresholds
| Confidence | Action |
|---|---|
| ≥ 70 | BUY CE |
| 45–69 | WAIT |
| ≤ 30 | BUY PE |

---

## Paper Trading

Paper trades are stored in **browser localStorage** — they persist across refreshes on the same browser.

### Lot Sizes
| Index | Lot Size |
|---|---|
| NIFTY 50 | 75 |
| BANK NIFTY | 30 |
| FIN NIFTY | 65 |
| SENSEX | 20 |

### P&L Calculation
```
BUY CE:  PnL = (current_atm_ce - entry_ce) × lot_size × lots
BUY PE:  PnL = (current_atm_pe - entry_pe) × lot_size × lots
```
> Current price uses the live ATM premium from the last signal scan. This is an approximation — real P&L depends on exact strike movement.

---

## Candlestick Patterns Detected
- Doji
- Hammer / Hanging Man
- Inverted Hammer / Shooting Star
- Bullish Engulfing / Bearish Engulfing
- Morning Star ⭐ (3-candle bullish reversal)
- Evening Star ⭐ (3-candle bearish reversal)
- Inside Bar
- Bullish Pin Bar / Bearish Pin Bar
- Three White Soldiers / Three Black Crows

---

## Fibonacci Levels (from 50-candle swing)
`0%` → `23.6%` → `38.2%` → `50%` → `61.8%` → `78.6%` → `100%`

Golden zones: **38.2%** and **61.8%**

## Camarilla Pivots (from previous day H/L/C)
`H4` (major resistance) → `H3` → `H2` → `H1` → `L1` → `L2` → `L3` → `L4` (major support)

Breakout above H4 or below L4 = strong trend continuation signal.

---

## Known Limitations
- **OI data** requires Angel One account + valid API credentials. Without it, scores rely on Technical (45%) + Smart Money (30%) + Sentiment (25%).
- **Paper trade P&L** approximates using current ATM price; not exact if strike has moved significantly ITM/OTM.
- **5m data** only available for last 2 days (Yahoo Finance limit).
- **ML model** trained on only 5 features — retrain with `train_model.py` using more features for better accuracy.
- Render free tier cold-starts after 15 min idle — first scan may take 30–60s.

---

## Disclaimer
This software is for **educational and paper trading purposes only**. Past signals do not guarantee future performance. The authors are not SEBI-registered advisors. Use at your own risk.
