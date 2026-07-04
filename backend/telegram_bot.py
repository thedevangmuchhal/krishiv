import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# To prevent spamming the exact same signal multiple times per ticker
_last_sent_signals = {}

def send_telegram_alert(signal_data: dict, ticker: str = "^NSEI"):
    global _last_sent_signals
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    action = signal_data.get("action", "WAIT")
    btst_action = signal_data.get("btst_action", "NO BTST")
    
    ml_data = signal_data.get("ml_prediction", {})
    ml_pred = ml_data.get("prediction", "WAIT")
    ml_conf = ml_data.get("probability", 0)
    
    ml_action = False
    if (ml_pred == "Bullish" or ml_pred == "Bearish") and ml_conf > 60:
        ml_action = True
    
    # Check for multi-signals (Phase 5)
    multi_signals = signal_data.get("multi_signals", [])
    has_any_active = any(s.get("action", "WAIT") != "WAIT" for s in multi_signals)
    
    # We only want to send alerts if there's an active trade
    if action == "WAIT" and ("NO BTST" in btst_action or not btst_action) and not ml_action and not has_any_active:
        return
        
    ticker_map = {"^NSEI": "NIFTY 50", "^NSEBANK": "BANK NIFTY", "NIFTY_FIN_SERVICE.NS": "FIN NIFTY"}
    ticker_name = ticker_map.get(ticker, ticker.replace(".NS", ""))
    
    msg = f"🚀 <b>{ticker_name} AI TRADING ALERT</b> 🚀\n\n"
    
    # ── TRADE CARD OVERRIDE ──
    trade_card = signal_data.get("trade_card")
    if trade_card:
        msg += f"<b>💳 NEW TRADE CARD</b>\n"
        msg += f"Entry : {trade_card.get('Entry')}\n"
        msg += f"Price : {trade_card.get('Price')}\n"
        msg += f"Target : {trade_card.get('Target')}\n"
        msg += f"Target Price : {trade_card.get('Target_Price')}\n"
        msg += f"SL : {trade_card.get('SL')}\n"
        msg += f"SL Price : {trade_card.get('SL_Price')}\n"
        msg += f"Confidence Level : {trade_card.get('Confidence_Level')}\n"
        msg += f"Last Backtested This Model : {trade_card.get('Last_Backtested')}\n\n"
    else:
        if action != "WAIT":
            msg += f"🎯 <b>INTRADAY SIGNAL:</b> {action}\n"
            
            # If it's a raw string message instead of full dict (used by auto-trader)
            if "LIVE TRADE EXECUTED" in action or "RISK EXIT" in action or "SQUARE-OFF" in action:
                msg = f"🚀 <b>AI TRADING EXECUTOR</b> 🚀\n\n{action}\n"
            else:
                msg += f"Entry: ₹{signal_data.get('entry_level')}\n"
                msg += f"Target: ₹{signal_data.get('target')}\n"
                msg += f"SL: ₹{signal_data.get('stop_loss')}\n\n"
            
        if ml_action:
            msg += f"🤖 <b>ML SHADOW SIGNAL:</b> {ml_data.get('strike')}\n"
            msg += f"Direction: {ml_pred} (Conf: {ml_conf}%)\n\n"
        
        # ── Multi-Strategy Risk Profiles (Phase 5) ──
        if multi_signals:
            icons = {"Safe": "🟢", "Normal": "🔵", "Optimal": "⭐", "Sniper": "🎯"}
            msg += "<b>Risk Profiles:</b>\n"
            for s in multi_signals:
                icon = icons.get(s["name"], "⚪")
                act = s["action"]
                if act == "WAIT":
                    msg += f"{icon} {s['name']}: WAIT ({s['reason']})\n"
                else:
                    msg += f"{icon} {s['name']}: {act} ✅\n"
            msg += "\n"
        
    if btst_action and "NO BTST" not in btst_action:
        msg += f"🌙 <b>BTST SIGNAL:</b> {btst_action}\n"
        msg += f"Entry: ₹{signal_data.get('btst_entry')}\n"
        msg += f"Target: ₹{signal_data.get('btst_target')}\n"
        msg += f"SL: ₹{signal_data.get('btst_sl')}\n\n"
        
    # Prevent duplicate spamming for this ticker
    if msg == _last_sent_signals.get(ticker):
        return
        
    _last_sent_signals[ticker] = msg
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    }
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram Error: {e}")

def send_telegram_startup_message():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    msg = "🚀 <b>Trading Backend is Live!</b>\nTelegram Bot Connected successfully."
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram Error: {e}")

def send_telegram_test_message():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "Credentials missing"
    msg = "👋 <b>Hello!</b>\nThis is a manual test message from your Trading Dashboard. Connection is working perfectly!"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            return True, "Message sent successfully!"
        else:
            return False, f"Telegram API returned {res.status_code}"
    except Exception as e:
        return False, str(e)
