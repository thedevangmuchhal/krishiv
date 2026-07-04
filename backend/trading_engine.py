import os
import time
import csv
from datetime import datetime
from data_fetcher import get_angel_session, get_filtered_angel_options, get_available_margin, get_live_positions

# ─────────────────────────────────────────────────────────────────────────────
# LIVE TRADING STATE & TRACKING
# ─────────────────────────────────────────────────────────────────────────────
_open_position = None
_virtual_position = None  # Tracks paper trades when auto-trading is OFF

# Full structure:
# {
#   "type": "CE" or "PE",
#   "direction": "BUY" or "SELL",  (BUY=Bullish/CE, SELL=Bearish/PE)
#   "symbol": "NIFTY...",
#   "token": "1234",
#   "qty": 25,
#   "entry_time": unix_timestamp,
#   "index_price_at_entry": 24300.0,  (NIFTY index price when trade was taken)
#   "atr_at_entry": 45.0,            (ATR value for stop-loss calculation)
# }

def get_open_position():
    """Returns the current open position dict, or None. Syncs with actual broker data."""
    global _open_position
    
    # 1. Fetch real positions from broker to see if user took a manual trade or squared off manually
    live_positions = get_live_positions()
    
    if not live_positions:
        _open_position = None
        return None
        
    # Find the first Intraday Option position
    for p in live_positions:
        # Example symbol: NIFTY15FEB2421500CE
        if p.get('instrumenttype') in ['OPTIDX', 'OPTSTK'] or ('CE' in p.get('tradingsymbol', '') or 'PE' in p.get('tradingsymbol', '')):
            net_qty = int(p.get('netqty', 0))
            if net_qty != 0:
                # We have a live position! Update internal tracker if it's new
                if _open_position is None or _open_position['symbol'] != p['tradingsymbol']:
                    _open_position = {
                        "type": "CE" if "CE" in p['tradingsymbol'] else "PE",
                        "direction": "BUY" if net_qty > 0 else "SELL",
                        "symbol": p['tradingsymbol'],
                        "token": p.get('symboltoken', ''),
                        "qty": abs(net_qty),
                        "entry_time": time.time(),
                        "index_price_at_entry": float(p.get('buyavgprice', 0)) if net_qty > 0 else float(p.get('sellavgprice', 0)), # Approximate
                        "atr_at_entry": 40.0, # Default fallback for manual trades
                        "best_pnl_pct": 0.0,
                    }
                return _open_position
                
    # If we had a position but it's not in live_positions, it was closed manually
    _open_position = None
    return None

def get_virtual_position():
    return _virtual_position

def set_virtual_position(action: str, symbol: str, token: str, index_price: float, atr_value: float):
    global _virtual_position
    _virtual_position = {
        "type": "CE" if "CE" in symbol else "PE",
        "direction": action,
        "symbol": symbol,
        "token": str(token),
        "qty": 25, # dummy qty for paper trading
        "entry_time": time.time(),
        "index_price_at_entry": index_price,
        "atr_at_entry": atr_value,
        "best_pnl_pct": 0.0,
    }
    return _virtual_position

def clear_virtual_position():
    global _virtual_position
    _virtual_position = None

def log_trade(action: str, symbol: str, entry_price: float, exit_price: float, pnl_pct: float, reason: str):
    """Logs trades and exits directly to the configured Google Sheet via Apps Script webhook."""
    try:
        from signal_logger import _post_to_sheet, _SHEET_URL
        if not _SHEET_URL:
            # Fallback to CSV if logger is not started via frontend
            file_path = "trade_log.csv"
            file_exists = os.path.isfile(file_path)
            with open(file_path, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                if not file_exists:
                    writer.writerow(["Timestamp", "Action", "Symbol", "Entry Price", "Exit Price", "PnL %", "Reason"])
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    action, symbol, 
                    round(entry_price, 2), 
                    round(exit_price, 2), 
                    f"{pnl_pct*100:.2f}%", 
                    reason
                ])
            return

        ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        time_str = ist_now.strftime("%H:%M:%S")

        is_entry = "ENTRY" in action
        
        row_data = {
            "type": "ENTRY" if is_entry else "EXIT",
            "entry_time": time_str if is_entry else "", # If exit, ideally we pass actual entry time, but script auto-matches open trades
            "spot_price": entry_price if is_entry else exit_price,
            "trade": symbol,
            "entry_premium": entry_price if is_entry else "",
            "exit_time": time_str if not is_entry else "",
            "exit_spot": exit_price if not is_entry else "",
            "exit_premium": exit_price if not is_entry else "",
            "pnl_points": round(pnl_pct * 100, 2) if not is_entry else "",
            "pnl_rupees": "", # Can be calculated on sheet
            "confidence": "",
            "signal_strength": "",
            "mtf": "",
            "reasons": reason,
            "remark": "Live Engine Trade",
            "duration_mins": "",
        }
        
        # If it's an exit, we need to provide the trade symbol so the script finds the open row
        if not is_entry:
            row_data["trade"] = symbol
            
        _post_to_sheet(row_data)
        
    except Exception as e:
        print(f"[Logger] Error writing to Sheet: {e}")

def get_option_contract(base_symbol, strike, option_type):
    """
    Finds the exact Angel One symbol and token for a specific strike and type (CE/PE).
    """
    angel_base = "NIFTY"
    base_upper = base_symbol.upper()
    if base_upper in ["^NSEI", "NIFTY", "NIFTY 50", "NIFTY50"]: angel_base = "NIFTY"
    elif base_upper in ["^NSEBANK", "BANK NIFTY", "BANKNIFTY", "BANK"]: angel_base = "BANKNIFTY"
    elif base_upper in ["NIFTY_FIN_SERVICE.NS", "FIN NIFTY", "FINNIFTY"]: angel_base = "FINNIFTY"
    
    opts = get_filtered_angel_options(angel_base)
    if not opts:
        return None, None
        
    def parse_expiry(date_str):
        try:
            return datetime.strptime(date_str, "%d%b%Y")
        except:
            return datetime.max
            
    valid_opts = [x for x in opts if x.get("expiry")]
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    valid_opts = [x for x in valid_opts if parse_expiry(x["expiry"]) >= now]
    if not valid_opts: return None, None
    
    valid_opts.sort(key=lambda x: parse_expiry(x["expiry"]))
    nearest_expiry = valid_opts[0]["expiry"]
    
    current_expiry_opts = [x for x in valid_opts if x["expiry"] == nearest_expiry]
    
    for opt in current_expiry_opts:
        try:
            opt_strike = float(opt["strike"]) / 100
        except:
            continue
        if opt_strike == strike and opt["symbol"].endswith(option_type):
            return opt["symbol"], opt["token"]
            
    return None, None

def place_market_order(action: str, strike: float, qty_lots: int = 1, base_symbol: str = "^NSEI",
                       index_price: float = 0, atr_value: float = 0):
    """
    Executes a live market order using the Angel One API.
    action: "BUY" (Bullish → buy CE) or "SELL" (Bearish → buy PE).
    index_price & atr_value: stored for live risk management (stop-loss calculation).
    """
    global _open_position
    
    if _open_position is not None:
        print(f"[Trading Engine] Skipped entry: Already in a position ({_open_position['symbol']}).")
        return False, "Already in position"

    session = get_angel_session()
    if not session:
        print("[Trading Engine] Angel API session not connected.")
        return False, "Not connected"
        
    option_type = "CE" if action == "BUY" else "PE"
    
    symbol, token = get_option_contract(base_symbol, strike, option_type)
    if not symbol or not token:
        print(f"[Trading Engine] Could not find contract for {strike} {option_type}.")
        return False, "Contract not found"
        
    # --- DYNAMIC SIZING CALCULATOR ---
    margin = get_available_margin()
    # Assume ATM option is roughly 0.5% to 1% of index price. Let's fetch actual LTP or estimate it.
    # For a safer approach without another API call, we estimate NIFTY ATM is ~150 Rs, BankNifty is ~300 Rs.
    est_premium = index_price * 0.007 if index_price > 0 else (150 if base_symbol == "^NSEI" else 300)
    
    lot_size = 25 if base_symbol == "^NSEI" else (15 if base_symbol == "^NSEBANK" else 25)
    
    # Calculate how many lots we can buy with 90% of available margin
    usable_margin = margin * 0.90
    cost_per_lot = est_premium * lot_size
    
    calculated_lots = int(usable_margin / cost_per_lot) if cost_per_lot > 0 else 0
    
    # If account is tiny or formula fails, fallback to qty_lots from env
    final_lots = max(calculated_lots, qty_lots) if margin > 10000 else qty_lots
    
    total_qty = final_lots * lot_size
    print(f"[Trading Engine] Margin: Rs.{margin:.2f} | Est Premium: Rs.{est_premium:.2f} | Buying {final_lots} lots (Qty {total_qty})")
    
    orderparams = {
        "variety": "NORMAL",
        "tradingsymbol": symbol,
        "symboltoken": str(token),
        "transactiontype": "BUY",  # We always BUY options (Option Buyers)
        "exchange": "NFO",
        "ordertype": "MARKET",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "quantity": str(total_qty)
    }
    
    try:
        print(f"[Trading Engine] PLACING LIVE ORDER: {orderparams}")
        orderId = session.placeOrder(orderparams)
        print(f"[Trading Engine] Order Success! ID: {orderId}")
        
        _open_position = {
            "type": option_type,
            "direction": action,
            "symbol": symbol,
            "token": str(token),
            "qty": total_qty,
            "entry_time": time.time(),
            "index_price_at_entry": index_price,
            "atr_at_entry": atr_value,
            "best_pnl_pct": 0.0,
        }
        print(f"[Trading Engine] Position tracked: {action} {option_type} @ index {index_price}, ATR={atr_value}")
        
        # Log to CSV
        log_trade("ENTRY BUY" if action == "BUY" else "ENTRY SELL", symbol, index_price, 0.0, 0.0, "AI Breakout Detected")
        
        return True, f"Placed {option_type} Order: {orderId}"
    except Exception as e:
        print(f"[Trading Engine] Order Failed: {e}")
        return False, str(e)

def square_off():
    """
    Squares off any open position. Used for 3:15 PM Intraday exit or ML exit.
    """
    global _open_position
    if _open_position is None:
        return False, "No open position"
        
    session = get_angel_session()
    if not session:
        return False, "Not connected"
        
    orderparams = {
        "variety": "NORMAL",
        "tradingsymbol": _open_position["symbol"],
        "symboltoken": _open_position["token"],
        "transactiontype": "SELL",  # Sell to close the bought option
        "exchange": "NFO",
        "ordertype": "MARKET",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "quantity": str(_open_position["qty"])
    }
    
    try:
        print(f"[Trading Engine] SQUARING OFF: {orderparams}")
        orderId = session.placeOrder(orderparams)
        print(f"[Trading Engine] Square-off Success! ID: {orderId}")
        _open_position = None
        return True, f"Squared off order: {orderId}"
    except Exception as e:
        print(f"[Trading Engine] Square-off Failed: {e}")
        return False, str(e)

def check_exit_conditions(pos_dict: dict, current_index_price: float, ml_prediction: str = "WAIT", ml_confidence: float = 0):
    """
    Evaluates whether an open position should be exited based on:
    1. Stop-Loss: 2x ATR breach (matches backtest logic exactly)
    2. ML Reversal: ML model flips direction with >60% confidence
    Returns: (should_exit: bool, reason: str, pnl_pct: float)
    """
    if not pos_dict:
        return False, "No position", 0.0
    
    entry_price = pos_dict.get("index_price_at_entry", 0)
    atr = pos_dict.get("atr_at_entry", 0)
    direction = pos_dict.get("direction", "BUY")
    
    if entry_price == 0 or atr == 0:
        print("[Risk Manager] WARNING: Missing entry_price or ATR — cannot evaluate stop-loss.")
        return False, "Missing risk data", 0.0
    
    # Calculate P&L percentage based on index movement
    if direction == "BUY":  # We bought CE, profit if index goes UP
        pnl_pct = (current_index_price - entry_price) / entry_price
    else:  # We bought PE, profit if index goes DOWN
        pnl_pct = (entry_price - current_index_price) / entry_price
        
    # Update best_pnl_pct for trailing stop
    best_pnl = pos_dict.get("best_pnl_pct", 0.0)
    if pnl_pct > best_pnl:
        pos_dict["best_pnl_pct"] = pnl_pct
        best_pnl = pnl_pct
        
    # 1. TRAILING STOP-LOSS CHECK: 50% Trailing
    if best_pnl > 0.001:
        trail_threshold = best_pnl * 0.5
        if pnl_pct < trail_threshold:
            reason = (f"📉 TRAILING STOP HIT: Profit dropped to {pnl_pct*100:.2f}% "
                      f"(Peak was {best_pnl*100:.2f}%). Locked in profits.")
            print(f"[Risk Manager] {reason}")
            return True, reason, pnl_pct
    
    # 2. FIXED STOP-LOSS CHECK: 2x ATR
    stop_loss_pct = 2.0 * atr / entry_price
    if pnl_pct < -stop_loss_pct:
        reason = (f"🛑 STOP-LOSS HIT: Index moved {pnl_pct*100:.2f}% against us "
                  f"(SL threshold: {-stop_loss_pct*100:.2f}%). Entry: {entry_price}, Now: {current_index_price}")
        print(f"[Risk Manager] {reason}")
        return True, reason, pnl_pct
    
    # 2. ML REVERSAL CHECK: ML flips direction with >60% confidence
    if direction == "BUY" and ml_prediction == "Bearish" and ml_confidence > 60:
        reason = f"🔄 ML REVERSAL: Was BUY but ML now Bearish ({ml_confidence}% conf). Cutting position."
        print(f"[Risk Manager] {reason}")
        return True, reason, pnl_pct
    elif direction == "SELL" and ml_prediction == "Bullish" and ml_confidence > 60:
        reason = f"🔄 ML REVERSAL: Was SELL but ML now Bullish ({ml_confidence}% conf). Cutting position."
        print(f"[Risk Manager] {reason}")
        return True, reason, pnl_pct
    
    # Position is safe
    return False, f"Position OK: P&L {pnl_pct*100:+.2f}%", pnl_pct
