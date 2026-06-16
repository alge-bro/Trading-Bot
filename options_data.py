#options_data.py
import os
import json
import yfinance as yf
import pandas as pd
from datetime import datetime

POSITIONS_FILE = "positions.json"

def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_positions(positions):
    with open(POSITIONS_FILE, 'w') as f:
        json.dump(positions, f, indent=4)

def get_option_chain(symbol):
    ticker = yf.Ticker(symbol)
    expirations = ticker.options
    nearest_exp = expirations[0]
    options = ticker.option_chain(nearest_exp).calls
    options['expiration'] = nearest_exp
    return options

def get_iv_percentile(symbol, days=30):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=f"{days}d", interval="1d")
    if hist.empty:
        return None
    iv_values = hist['Close'].pct_change().abs().dropna()
    current_iv = iv_values.iloc[-1]
    percentile = (iv_values < current_iv).sum() / len(iv_values)
    return percentile

def is_near_earnings(symbol):
    ticker = yf.Ticker(symbol)
    try:
        cal = ticker.calendar
        earnings_date = pd.to_datetime(cal.loc['Earnings Date'][0])
        return (earnings_date - pd.Timestamp.now()).days <= 5
    except:
        return False

def _filter_and_score_options(df, current_price):
    df['spread'] = df['ask'] - df['bid']
    df['spread_pct'] = df['spread'] / df['ask'].replace(0, 0.01)
    df['strike_distance'] = abs(df['strike'] - current_price)

    filtered = df[
        (df['lastPrice'] >= 0.20) &
        (df['openInterest'] > 50) &
        (df['volume'] > 10) &
        (df['bid'] > 0) &
        (df['ask'] > 0) &
        (df['spread_pct'] < 0.15)
    ].copy()

    if filtered.empty:
        return None

    filtered['fill_price'] = (filtered['bid'] + filtered['ask']) / 2
    filtered['score'] = (
        (1.0 / (1 + filtered['strike_distance'])) * 0.4 +
        (1.0 - filtered['spread_pct']) * 0.3 +
        (filtered['volume'] / filtered['volume'].max()) * 0.3
    )

    best_option = filtered.sort_values(by='score', ascending=False).iloc[0]

    return {
        'contract': best_option['contractSymbol'],
        'strike': best_option['strike'],
        'expiration': best_option.get('expiration', 'Unknown'),
        'last_price': round(best_option['fill_price'], 2),
        'bid': best_option['bid'],
        'ask': best_option['ask'],
        'volume': best_option['volume'],
        'score': round(best_option['score'], 3)
    }

def pick_option(symbol, current_price):
    try:
        stock = yf.Ticker(symbol)
        expirations = stock.options

        if not expirations:
            print(f"❌ No expiration dates found for {symbol}")
            return None

        today = datetime.today().date()
        expiration = next(
            (exp for exp in expirations if (datetime.strptime(exp, "%Y-%m-%d").date() - today).days >= 3),
            expirations[-1]
        )

        calls = stock.option_chain(expiration).calls.copy()
        calls['expiration'] = expiration

        if calls.empty:
            print(f"❌ No call options found for {symbol} on {expiration}")
            return None

        return _filter_and_score_options(calls, current_price)
    except Exception as e:
        print(f"failed to fetch CALL option for {symbol}: {e}")
        return None


def pick_put_option(symbol, current_price):
    try:
        stock = yf.Ticker(symbol)
        expirations = stock.options

        if not expirations:
            print(f"❌ No expiration dates found for {symbol}")
            return None

        today = datetime.today().date()
        expiration = next(
            (exp for exp in expirations if (datetime.strptime(exp, "%Y-%m-%d").date() - today).days >= 3),
            expirations[-1]
        )

        puts = stock.option_chain(expiration).puts.copy()
        puts['expiration'] = expiration

        if puts.empty:
            print(f"❌ No put options found for {symbol} on {expiration}")
            return None

        return _filter_and_score_options(puts, current_price)
    except Exception as e:
        print(f"failed to fetch PUT option for {symbol}: {e}")
        return None
