#options_data.py
import yfinance as yf
import pandas as pd
from datetime import datetime

# NOTE: load_positions / save_positions used to live here AND in
# sell_checker.py. They now live in positions.py (one source of truth).
# Removed from this file: get_option_chain (unused), and get_iv_percentile
# (it didn't compute implied volatility at all — it returned the percentile
# of the latest absolute daily return — and nothing called it).


def is_near_earnings(symbol, within_days=5):
    """True if earnings fall within `within_days`. Handy as a gamma-risk
    gate. Not wired in by default — to use it, early-return None from
    pick_option/pick_put_option when this is True.
    Handles both the new (dict) and legacy (DataFrame) yfinance calendar."""
    try:
        cal = yf.Ticker(symbol).calendar
        if isinstance(cal, dict):
            dates = cal.get('Earnings Date') or []
            earnings_date = pd.to_datetime(dates[0]) if dates else None
        else:  # legacy DataFrame layout
            earnings_date = pd.to_datetime(cal.loc['Earnings Date'][0])
        if earnings_date is None:
            return False
        return 0 <= (earnings_date - pd.Timestamp.now()).days <= within_days
    except Exception:
        return False


def _pick_expiration(expirations, min_days=3):
    today = datetime.today().date()
    return next(
        (exp for exp in expirations
         if (datetime.strptime(exp, "%Y-%m-%d").date() - today).days >= min_days),
        expirations[-1]
    )


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


def _pick(symbol, current_price, side):
    """side: 'calls' or 'puts'. Shared body for the two public functions."""
    try:
        stock = yf.Ticker(symbol)
        expirations = stock.options
        if not expirations:
            print(f"❌ No expiration dates found for {symbol}")
            return None

        expiration = _pick_expiration(expirations)
        chain = stock.option_chain(expiration)
        contracts = (chain.calls if side == 'calls' else chain.puts).copy()
        contracts['expiration'] = expiration

        if contracts.empty:
            print(f"❌ No {side} found for {symbol} on {expiration}")
            return None

        return _filter_and_score_options(contracts, current_price)
    except Exception as e:
        print(f"failed to fetch {side} option for {symbol}: {e}")
        return None


def pick_option(symbol, current_price):
    return _pick(symbol, current_price, 'calls')


def pick_put_option(symbol, current_price):
    return _pick(symbol, current_price, 'puts')