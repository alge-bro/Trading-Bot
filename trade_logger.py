# trade_logger.py
import csv
from datetime import datetime

LOG_FILE = 'trade_log.csv'

def log_trade(symbol, action, price):
    try:
        with open(LOG_FILE, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([datetime.now().isoformat(), symbol, action, price])
        print(f"📝 Logged trade: {symbol} {action} at ${price:.2f}")
    except Exception as e:
        print(f"❌ Failed to log trade: {e}")
