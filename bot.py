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
from datetime import datetime, time as dtime
import pytz
import yfinance as yf
import traceback
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

# Optional AI filter (uncomment if using)
# from ai_filter import ai_filter_approves

api = tradeapi.REST(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, config.ALPACA_ENDPOINT)

SYMBOLS = ['QQQ', 'SPY', 'INTC', 'SHOP', 'CLF', 'F', 'ET', 'DIS']


def fetch_data(symbol, timeframe='5Min', limit=100):
    try:
        bars = api.get_bars(symbol, timeframe, limit=limit).df
        if bars.empty or len(bars) < 30:
            print(f"[{symbol}] Low Alpaca bar count ({len(bars)}), preloading with yFinance")
            try:
                fallback = yf.download(
                    symbol,
                    period="2d",
                    interval="5m",
                    progress=False,
                    threads=False
                )
                if fallback.empty:
                    print(f"yFinance returned empty data for {symbol}")
                    return pd.DataFrame()
                fallback = fallback.reset_index()
                fallback.columns = [col.lower() for col in fallback.columns]
                fallback = fallback.rename(columns={
                    'datetime': 'timestamp',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume'
                })
                print(f"[{symbol}] Preloaded {len(fallback)} bars from yFinance")
                return fallback

            except Exception as yf_error:
                print(f"yFinance failed for {symbol}: {yf_error}")
                return pd.DataFrame()
        bars = bars.reset_index()
        bars.columns = bars.columns.str.lower()
        return bars
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()


def execute_trade(symbol, signal, option_data):
    if signal in ['BUY_CALL', 'BUY_PUT']:
        trade_type = "Call" if signal == 'BUY_CALL' else "Put"
        message = (f"{trade_type} {symbol} Option:\n"
                   f"\U0001F31F Strike: ${option_data['strike']}\n"
                   f"\U0001F514️ Expiration: {option_data['expiration']}\n"
                   f"\U0001F4B0 Premium: ${option_data['last_price']:.2f}\n"
                   f"\U0001F4DD Contract: {option_data['contract']}")
        send_sms(message)
        log_trade(symbol, f"{signal} ({option_data['contract']})", option_data['last_price'])
    else:
        print(f"[{symbol}] HOLD signal detected.")


def in_active_window():
    now = datetime.now(pytz.timezone('US/Eastern'))
    is_weekday = now.weekday() < 5
    market_open = dtime(9, 30)
    market_close = dtime(16, 0)
    return is_weekday and market_open <= now.time() <= market_close


if __name__ == "__main__":
    print("🚀 Multi-stock Options Bot starting!")
    required_rows = 30
    while True:
        try:
            if in_active_window():
                check_for_sell_opportunities(send_sms, log_trade)

                for symbol in SYMBOLS:
                    data = fetch_data(symbol)
                    print(f"[{symbol}] Pulled {len(data)} raw bars")
                    # Ensure we have enough raw data BEFORE applying indicators
                    if len(data) < required_rows:
                        print(f"⚠️ Skipping {symbol} — not enough raw data for indicators ({len(data)} rows)")
                        continue

                    data = add_all_indicators(data)
                    data = data.dropna()
                    clean_rows = len(data.dropna())

                    if clean_rows < required_rows:
                        print(
                            f"Skipping {symbol} - insufficient clean data after indicators ({clean_rows}/{required_rows})")
                        continue
                    else:
                        print(f"{symbol} ready for signal analysis with {clean_rows} clean rows")

                    signal = get_trade_signal(data)
                    current_price = data['close'].iloc[-1]

                    timestamp = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d %I:%M:%S %p')
                    print(f"[{timestamp}] {symbol} Signal: {signal} at ${current_price:.2f}")

                    option_data = None

                    if signal == 'BUY_CALL':
                        option_data = pick_option(symbol, current_price)
                    elif signal == 'BUY_PUT':
                        option_data = pick_put_option(symbol, current_price)

                    if option_data:
                        print(
                            f" Selected Option: {option_data['contract']} | Strike: {option_data['strike']} | Premium: ${option_data['last_price']:.2f}")
                        execute_trade(symbol, signal, option_data)
                    elif signal != 'HOLD':
                        print(f"No suitable option found for {symbol}.")

                    current_price = data['close'].iloc[-1]

                    timestamp = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d %I:%M:%S %p')
                    print(f"[{timestamp}] {symbol} Signal: {signal} at ${current_price:.2f}")

                    option_data = None

                    if signal == 'BUY_CALL':
                        option_data = pick_option(symbol, current_price)
                    elif signal == 'BUY_PUT':
                        option_data = pick_put_option(symbol, current_price)
                    if option_data:
                        print(
                            f"Selected Option: {option_data['contract']} | Strike: {option_data['strike']} | Premium: ${option_data['last_price']:.2f}")
                        execute_trade(symbol, signal, option_data)
                    elif signal != 'HOLD':
                        print(f"No suitable option found for {symbol}.")
            else:
                print(f"Outside active hours: {datetime.now(pytz.timezone('US/Eastern')).strftime('%A %I:%M %p')}")

            time.sleep(300)

        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()
            send_sms(f"Bot Error:{e}")
            time.sleep(60)
