# bot.py
import alpaca_trade_api as tradeapi
import pandas as pd
import time
import config
from indicators import add_all_indicators, get_trade_signal
from notifications import send_sms
from trade_logger import log_trade
from options_data import pick_option, pick_put_option
from sell_checker import check_for_sell_opportunities
from positions import has_open_position, add_position
from datetime import datetime, time as dtime
import pytz
import yfinance as yf
import traceback
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

# Optional AI filter (uncomment if using)
# from ai_filter import validate_trade

api = tradeapi.REST(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, config.ALPACA_ENDPOINT)

SYMBOLS = ['QQQ', 'SPY', 'INTC', 'SHOP', 'CLF', 'F', 'ET', 'DIS']
REQUIRED_ROWS = 30
EASTERN = pytz.timezone('US/Eastern')


def fetch_data(symbol, timeframe='5Min', limit=100):
    try:
        bars = api.get_bars(symbol, timeframe, limit=limit).df
        if bars.empty or len(bars) < 30:
            print(f"[{symbol}] Low Alpaca bar count ({len(bars)}), preloading with yFinance")
            return _yfinance_fallback(symbol)
        bars = bars.reset_index()
        bars.columns = bars.columns.str.lower()
        return bars
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()


def _yfinance_fallback(symbol):
    try:
        fallback = yf.download(
            symbol, period="2d", interval="5m",
            progress=False, threads=False, auto_adjust=False
        )
        if fallback.empty:
            print(f"yFinance returned empty data for {symbol}")
            return pd.DataFrame()

        # Single-ticker downloads now come back with MultiIndex columns
        # like ('Close', 'AAPL'). Flatten to the price field name. This is
        # the same trap backtest.py handles — bot.py was missing the guard
        # and would crash with "tuple has no attribute lower".
        if isinstance(fallback.columns, pd.MultiIndex):
            fallback.columns = fallback.columns.get_level_values(0)

        fallback = fallback.reset_index()
        fallback.columns = [str(c).lower() for c in fallback.columns]
        fallback = fallback.rename(columns={'datetime': 'timestamp', 'date': 'timestamp'})
        print(f"[{symbol}] Preloaded {len(fallback)} bars from yFinance")
        return fallback
    except Exception as yf_error:
        print(f"yFinance failed for {symbol}: {yf_error}")
        return pd.DataFrame()


def execute_trade(symbol, signal, option_data):
    """Alert + bookkeeping only. This does NOT submit a real broker order.
    If/when you want live execution, place the order with your broker HERE,
    confirm the fill, and only then call add_position(...)."""
    trade_type = "CALL" if signal == 'BUY_CALL' else "PUT"
    message = (f"{trade_type} {symbol} Option:\n"
               f"\U0001F31F Strike: ${option_data['strike']}\n"
               f"\U0001F514 Expiration: {option_data['expiration']}\n"
               f"\U0001F4B0 Premium: ${option_data['last_price']:.2f}\n"
               f"\U0001F4DD Contract: {option_data['contract']}")
    send_sms(message)
    log_trade(symbol, f"{signal} ({option_data['contract']})", option_data['last_price'])
    add_position(symbol, option_data, trade_type)  # <-- this is what makes selling possible


def in_active_window():
    now = datetime.now(EASTERN)
    is_weekday = now.weekday() < 5
    return is_weekday and dtime(9, 30) <= now.time() <= dtime(16, 0)


def process_symbol(symbol):
    data = fetch_data(symbol)
    print(f"[{symbol}] Pulled {len(data)} raw bars")

    if len(data) < REQUIRED_ROWS:
        print(f"⚠️ Skipping {symbol} — not enough raw data ({len(data)} rows)")
        return

    data = add_all_indicators(data).dropna()
    if len(data) < REQUIRED_ROWS:
        print(f"Skipping {symbol} — insufficient clean data after indicators ({len(data)} rows)")
        return

    signal = get_trade_signal(data)
    current_price = data['close'].iloc[-1]
    timestamp = datetime.now(EASTERN).strftime('%Y-%m-%d %I:%M:%S %p')
    print(f"[{timestamp}] {symbol} Signal: {signal} at ${current_price:.2f}")

    if signal not in ('BUY_CALL', 'BUY_PUT'):
        return  # HOLD

    # Don't pyramid into a symbol we're already holding.
    if has_open_position(symbol):
        print(f"[{symbol}] Already holding a position — skipping {signal}.")
        return

    option_data = (pick_option(symbol, current_price) if signal == 'BUY_CALL'
                   else pick_put_option(symbol, current_price))

    if option_data:
        print(f"Selected Option: {option_data['contract']} | Strike: {option_data['strike']} "
              f"| Premium: ${option_data['last_price']:.2f}")
        execute_trade(symbol, signal, option_data)
    else:
        print(f"No suitable option found for {symbol}.")


if __name__ == "__main__":
    print("🚀 Multi-stock Options Bot starting!")
    while True:
        try:
            if in_active_window():
                check_for_sell_opportunities(send_sms, log_trade)
                for symbol in SYMBOLS:
                    process_symbol(symbol)
            else:
                print(f"Outside active hours: {datetime.now(EASTERN).strftime('%A %I:%M %p')}")
            time.sleep(300)
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()
            send_sms(f"Bot Error: {e}")
            time.sleep(60)