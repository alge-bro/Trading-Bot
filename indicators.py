#indicators.py
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator, SMAIndicator, MACD
from ta.momentum import RSIIndicator, ROCIndicator
from ta.volatility import BollingerBands, AverageTrueRange

def add_all_indicators(data):
    data['EMA_9'] = EMAIndicator(data['close'], window=9).ema_indicator()
    data['SMA_50'] = SMAIndicator(data['close'], window=50).sma_indicator()
    data['RSI'] = RSIIndicator(data['close'], window=14).rsi()

    macd = MACD(data['close'], window_slow=26, window_fast=12, window_sign=9)
    data['MACD'] = macd.macd()
    data['MACD_signal'] = macd.macd_signal()

    bb = BollingerBands(data['close'], window=20, window_dev=2)
    data['BB_high'] = bb.bollinger_hband()
    data['BB_low'] = bb.bollinger_lband()

    data['ATR'] = AverageTrueRange(
        high=data['high'], low=data['low'], close=data['close'], window=14
    ).average_true_range()

    data['ROC'] = ROCIndicator(close=data['close'], window=5).roc()

    return add_candle_patterns(data)

def add_candle_patterns(data):
    body = abs(data['close'] - data['open'])
    range_ = data['high'] - data['low']

    data['doji'] = (body / (range_ + 1e-6)) < 0.1

    data['hammer'] = (
        (range_ > 3 * body) &
        ((data['close'] - data['low']) / (range_ + 1e-6) > 0.6) &
        ((data['high'] - data['open']) / (range_ + 1e-6) < 0.3)
    )

    data['shooting_star'] = (
        (range_ > 3 * body) &
        ((data['high'] - data['open']) / (range_ + 1e-6) > 0.6) &
        ((data['close'] - data['low']) / (range_ + 1e-6) < 0.3)
    )

    return data

def get_support_resistance(data, window=20):
    recent = data.tail(window)
    support = recent['low'].min()
    resistance = recent['high'].max()
    return support, resistance

def get_trade_signal(data, verbose=False):
    """
    Computes weighted signal score and returns 'BUY_CALL', 'BUY_PUT', or 'HOLD'.
    """
    if len(data) < 2:
        return 'HOLD'  # Not enough rows

    try:
        current = data.iloc[-1]
        previous = data.iloc[-2]
    except IndexError as e:
        print(f"⚠️ Not enough data rows: {len(data)} — {e}")
        return 'HOLD'


    ema_up = previous['EMA_9'] < previous['SMA_50'] and current['EMA_9'] > current['SMA_50']
    ema_down = previous['EMA_9'] > previous['SMA_50'] and current['EMA_9'] < current['SMA_50']
    rsi = current['RSI']
    price = current['close']

    support, resistance = get_support_resistance(data)
    hammer = current.get('hammer', False)
    shooting_star = current.get('shooting_star', False)

    atr = current['ATR']
    roc = current['ROC']

    atr_threshold = 0.5
    roc_threshold = 0.3

    buy_score = 0
    if ema_up: buy_score += 1.0
    if hammer: buy_score += 0.5
    if rsi < 50: buy_score += 0.5
    if atr > atr_threshold: buy_score += 0.5
    if roc > roc_threshold: buy_score += 0.5
    if price > support * 1.01: buy_score += 0.5

    sell_score = 0
    if ema_down: sell_score += 1.0
    if shooting_star: sell_score += 0.5
    if rsi > 60: sell_score += 0.5
    if atr > atr_threshold: sell_score += 0.5
    if roc < -roc_threshold: sell_score += 0.5
    if price < resistance * 0.99: sell_score += 0.5

    if verbose:
        print(f"🧪 BUY Score: {buy_score:.2f} | EMA_up: {ema_up} | Hammer: {hammer} | RSI: {rsi:.2f} | ATR: {atr:.2f} | ROC: {roc:.2f}")
        print(f"🧪 SELL Score: {sell_score:.2f} | EMA_down: {ema_down} | Shooting Star: {shooting_star} | RSI: {rsi:.2f} | ATR: {atr:.2f} | ROC: {roc:.2f}")
        print("-" * 100)

    if buy_score >= 2.5:
        return 'BUY_CALL'
    elif sell_score >= 2.5:
        return 'BUY_PUT'
    else:
        return 'HOLD'
