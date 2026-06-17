# signals.py

# Tweak these if you like in one place
SIG_KWARGS = dict(
    atr_thresh=0.15,
    roc_thresh=0.08,
    blow_atr_mult=1.1,
    blow_pct=0.002,
    vol_mult=1.1,
    donchian_lookback=8
)

def generate_signal(df, idx,
                    atr_thresh, roc_thresh,
                    blow_atr_mult, blow_pct,
                    vol_mult, donchian_lookback):
    buy = sell = 0.0

    # EMA/SMA cross
    p, e  = df['EMA_9'].iat[idx-1], df['SMA_50'].iat[idx-1]
    c, e2 = df['EMA_9'].iat[idx],   df['SMA_50'].iat[idx]
    if p < e and c > e2: buy  += 1.0
    if p > e and c < e2: sell += 1.0

    # Hammer/Shooting Star
    if df['hammer'].iat[idx]:        buy  += 0.5
    if df['shooting_star'].iat[idx]: sell += 0.5

    # RSI
    if df['RSI'].iat[idx] < 55: buy  += 0.5
    if df['RSI'].iat[idx] > 45: sell += 0.5

    # MACD hist
    mh = df['MACD'].iat[idx] - df['MACD_signal'].iat[idx]
    if mh > 0: buy  += 1.0
    if mh < 0: sell += 1.0

    # ATR (already normalized in indicators.py; raw value vs threshold here)
    if df['ATR'].iat[idx] > atr_thresh:
        buy  += 1.0
        sell += 1.0

    # ROC
    if df['ROC'].iat[idx] >  roc_thresh: buy  += 0.5
    if df['ROC'].iat[idx] < -roc_thresh: sell += 0.5

    # Bollinger Bands (columns set by add_all_indicators)
    if df['close'].iat[idx] > df['BB_high'].iat[idx]: buy  += 0.5
    if df['close'].iat[idx] < df['BB_low'].iat[idx]:  sell += 0.5

    # Intrabar ATR spike
    ir = df['high'].iat[idx] - df['low'].iat[idx]
    if ir > blow_atr_mult * df['ATR'].iat[idx]:
        if df['close'].iat[idx] > df['open'].iat[idx]: buy  += 0.5
        else:                                           sell += 0.5

    # Close-to-Open %
    ro1 = (df['close'].iat[idx] - df['open'].iat[idx]) / df['open'].iat[idx]
    if ro1 >  blow_pct: buy  += 0.5
    if ro1 < -blow_pct: sell += 0.5

    # Volume spike
    avgv = df['volume'].iloc[max(0, idx - donchian_lookback):idx].mean()
    if df['volume'].iat[idx] > vol_mult * avgv:
        if df['close'].iat[idx] > df['open'].iat[idx]: buy  += 0.5
        else:                                           sell += 0.5

    # Donchian breakout
    dh = df['high'].iloc[max(0, idx - donchian_lookback):idx].max()
    dl = df['low'].iloc[max(0, idx - donchian_lookback):idx].min()
    if df['close'].iat[idx] > dh: buy  += 1.0
    if df['close'].iat[idx] < dl: sell += 1.0

    if buy > sell:
        return 'BUY_CALL'
    elif sell > buy:
        return 'BUY_PUT'
    else:
        return 'HOLD'
