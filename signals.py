# signals.py

from indicators import bollinger_bands

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
    p,e = df['ema9'].iat[idx-1], df['sma50'].iat[idx-1]
    c,e2= df['ema9'].iat[idx],   df['sma50'].iat[idx]
    if p < e and c > e2: buy  += 1.0
    if p > e and c < e2: sell += 1.0

    # Hammer/Star
    if df['hammer'].iat[idx]: buy  += 0.5
    if df['star'].iat[idx]:   sell += 0.5

    # RSI
    if df['rsi'].iat[idx] < 55:  buy  += 0.5
    if df['rsi'].iat[idx] > 45:  sell += 0.5

    # MACD hist
    mh = df['macd'].iat[idx] - df['macd_sig'].iat[idx]
    if mh > 0: buy  += 1.0
    if mh < 0: sell += 1.0

    # ATR
    if df['atr'].iat[idx] > atr_thresh:
        buy  += 1.0
        sell += 1.0

    # ROC
    if df['roc'].iat[idx] > roc_thresh:    buy  += 0.5
    if df['roc'].iat[idx] < -roc_thresh:   sell += 0.5

    # Bollinger
    u,_,l = bollinger_bands(df, period=20, std_dev=2)
    if df['close'].iat[idx] > u.iat[idx]: buy  += 0.5
    if df['close'].iat[idx] < l.iat[idx]: sell += 0.5

    # Intrabar ATR spike
    ir = df['high'].iat[idx] - df['low'].iat[idx]
    if ir > blow_atr_mult * df['atr'].iat[idx]:
        if df['close'].iat[idx] > df['open'].iat[idx]: buy  += 0.5
        else:                                      sell += 0.5

    # Close→Open %
    ro1 = (df['close'].iat[idx] - df['open'].iat[idx]) / df['open'].iat[idx]
    if ro1 > blow_pct:    buy  += 0.5
    if ro1 < -blow_pct:   sell += 0.5

    # Volume spike
    avgv = df['volume'].iloc[max(0,idx-donchian_lookback):idx].mean()
    if df['volume'].iat[idx] > vol_mult * avgv:
        if df['close'].iat[idx] > df['open'].iat[idx]: buy  += 0.5
        else:                                      sell += 0.5

    # Donchian
    dh = df['high'].iloc[max(0,idx-donchian_lookback):idx].max()
    dl = df['low'].iloc[max(0,idx-donchian_lookback):idx].min()
    if df['close'].iat[idx] > dh: buy  += 1.0
    if df['close'].iat[idx] < dl: sell += 1.0

    # Return
    if buy >= sell:
        return buy, ("BUY_CALL" if buy > sell else "HOLD")
    else:
        return sell, "BUY_PUT"
