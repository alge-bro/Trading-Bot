# sell_checker.py
import json
import os
import yfinance as yf
import time

POSITIONS_FILE = "positions.json"
SELL_THRESHOLD = 0.3  # 30% profit target


def safe_fetch_yfinance(fn, *args, retries=3, delay=1):
    for _ in range(retries):
        try:
            return fn(*args)
        except Exception as e:
            print(f"[yfinance] Retry due to error: {e}")
            time.sleep(delay)
    return None


def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_positions(positions):
    with open(POSITIONS_FILE, 'w') as f:
        json.dump(positions, f, indent=4)


def get_option_price(contract_symbol):
    option = safe_fetch_yfinance(yf.Ticker, contract_symbol)
    if not option:
        return None
    try:
        hist = option.history(period="1d", interval="1m")
        if hist.empty:
            return None
        return hist['Close'].iloc[-1]
    except Exception as e:
        print(f"Error fetching price for {contract_symbol}: {e}")
        return None


def check_for_sell_opportunities(send_sms, log_trade):
    positions = load_positions()
    updated_positions = positions.copy()

    for symbol, data in positions.items():
        contract = data['contract']
        buy_price = data['last_price']
        current_price = get_option_price(contract)

        if current_price is None:
            continue

        profit = (current_price - buy_price) / buy_price

        if profit >= SELL_THRESHOLD:
            message = (f"💵 SELL {symbol} Option:\n"
                       f"🌟 Target reached!\n"
                       f"📈 Bought: ${buy_price:.2f} → Now: ${current_price:.2f}\n"
                       f"📝 Contract: {contract}")
            send_sms(message)
            log_trade(symbol, f"SELL ({contract})", current_price)
            del updated_positions[symbol]  # Remove from active list

    save_positions(updated_positions)
    return updated_positions

def simulate_sell(entry_price, current_price):
    """
    Simulates whether we should sell based on a profit threshold.
    """
    if entry_price is None or current_price is None:
        return False

    profit = (current_price - entry_price) / entry_price
    return profit >= SELL_THRESHOLD
