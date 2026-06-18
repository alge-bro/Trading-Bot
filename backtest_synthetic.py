#backtest_synthetic.py
"""
Synthetic options backtest + experiment harness (Road A).

Why synthetic: yfinance has NO historical option prices, so the old backtest.py
priced every trade with today's live chain -- fiction. This never fetches an
option price. It runs your EXISTING signal over the underlying, prices a
hypothetical option with Black-Scholes, decays it bar by bar, and exits on your
real rules (take-profit / stop-loss / max-hold / expiry).

What's new in this version:
  * Parameters live in a Params object, so we can SWEEP many configs in one run.
  * Each symbol's data is fetched ONCE and cached to disk -> sweeping is fast and
    doesn't hammer Yahoo.
  * Honest fractional position sizing -> the equity curve and drawdown actually
    mean something (the old "compounded -100%" was an all-in artifact).

WHERE THE MODEL LIES (unchanged, still true):
  IV held constant at entry (captures theta + delta, blind to vega / IV-crush);
  no vol skew; spread is a flat % haircut; fills assumed instant. This is a
  SIGNAL SIEVE, not a P&L oracle. A good result here = permission to buy real
  data (Road B), not permission to trade.
"""

import os
import math
import pickle
from dataclasses import dataclass, replace
from datetime import timedelta, datetime

import numpy as np
import pandas as pd
import yfinance as yf

from indicators import add_all_indicators, get_trade_signal

SYMBOLS = ['AAPL', 'MSFT', 'NVDA', 'AMD', 'TSLA', 'META', 'AMZN', 'GOOGL',
           'NFLX', 'PLTR', 'SPY', 'QQQ', 'COIN', 'SOFI']
INTERVAL = "5m"
DAYS_BACK = 60
CACHE_DIR = ".cache"

_BARS_PER_DAY = {"1m": 390, "5m": 78, "15m": 26, "30m": 13, "1h": 7, "1d": 1}


@dataclass(frozen=True)
class Params:
    dte_days: int = 7          # days to expiry at entry
    moneyness: float = 0.00    # 0=ATM, +0.02 = 2% OTM
    risk_free: float = 0.04
    take_profit: float = 0.30
    stop_loss: float = -0.50
    max_hold_hours: float = 6.0
    signal_threshold: float = 2.5
    spread_pct: float = 0.06   # round-trip bid/ask cost
    min_premium: float = 0.20
    vol_lookback: int = 50
    vol_floor: float = 0.10
    vol_cap: float = 2.00
    risk_per_trade: float = 0.10   # fraction of equity committed per trade (sizing)


# ----------------------------- pricing -----------------------------

def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _intrinsic(kind, S, K):
    return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)


def bs_price(kind, S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return _intrinsic(kind, S, K)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if kind == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def estimate_vol(closes, bars_per_year, p):
    rets = np.log(closes / closes.shift(1)).dropna().tail(p.vol_lookback)
    if len(rets) < 2:
        return p.vol_floor
    sigma = float(rets.std() * math.sqrt(bars_per_year))
    return min(max(sigma, p.vol_floor), p.vol_cap)


def _year_fraction(t_now, expiry):
    return (expiry - t_now).total_seconds() / (365.0 * 24 * 3600)


# ----------------------------- engine ------------------------------

def run_backtest_on_frame(df_ind, symbol, p, interval=INTERVAL):
    """df_ind must already have indicators (add_all_indicators) applied.
    Pure function -- no network -- so the sweep can call it many times cheaply."""
    bars_per_year = 252 * _BARS_PER_DAY.get(interval, 78)
    start = max(60, int(df_ind['SMA_50'].isna().sum()) + 1)
    trades = []
    open_trade = None

    for i in range(start, len(df_ind)):
        sub = df_ind.iloc[:i + 1]            # causal: no peeking forward
        S = float(df_ind['close'].iat[i])
        t_now = df_ind.index[i]
        if not np.isfinite(S) or S <= 0:
            continue

        if open_trade is None:
            signal = get_trade_signal(sub, threshold=p.signal_threshold)
            if signal not in ('BUY_CALL', 'BUY_PUT'):
                continue
            kind = 'call' if signal == 'BUY_CALL' else 'put'
            sigma = estimate_vol(sub['close'], bars_per_year, p)
            K = round(S * (1 + p.moneyness), 2) if kind == 'call' else round(S * (1 - p.moneyness), 2)
            expiry = t_now + timedelta(days=p.dte_days)
            theo = bs_price(kind, S, K, _year_fraction(t_now, expiry), p.risk_free, sigma)
            entry_fill = theo * (1 + p.spread_pct / 2)
            if entry_fill < p.min_premium:
                continue
            open_trade = dict(symbol=symbol, kind=kind, strike=K, sigma=sigma,
                              expiry=expiry, entry_time=t_now, entry_fill=entry_fill)
        else:
            T = _year_fraction(t_now, open_trade['expiry'])
            expired = T <= 0
            theo = (_intrinsic(open_trade['kind'], S, open_trade['strike']) if expired
                    else bs_price(open_trade['kind'], S, open_trade['strike'], T,
                                  p.risk_free, open_trade['sigma']))
            exit_fill = max(theo * (1 - p.spread_pct / 2), 0.0)
            ret = (exit_fill - open_trade['entry_fill']) / open_trade['entry_fill']
            held_h = (t_now - open_trade['entry_time']).total_seconds() / 3600

            reason = ("take-profit" if ret >= p.take_profit else
                      "stop-loss" if ret <= p.stop_loss else
                      "max-hold" if held_h >= p.max_hold_hours else
                      "expiry" if expired else None)
            if reason:
                open_trade.update(exit_time=t_now, return_pct=round(ret * 100, 2),
                                  reason=reason, held_hours=round(held_h, 2))
                trades.append(open_trade)
                open_trade = None
    return trades


def compute_metrics(all_trades, p, label="config"):
    if not all_trades:
        return dict(label=label, trades=0)
    df = pd.DataFrame(all_trades).sort_values('exit_time').reset_index(drop=True)
    rets = df['return_pct'] / 100.0

    # Fractional sizing: commit `risk_per_trade` of equity to each position.
    # A -90% trade now costs risk_per_trade*90% of equity, not the whole account.
    equity = (1 + p.risk_per_trade * rets).cumprod()
    max_dd = (equity / equity.cummax() - 1).min() * 100

    counts = df['reason'].value_counts().to_dict()
    n = len(df)
    avg = df['return_pct'].mean()
    std = df['return_pct'].std(ddof=1) if n > 1 else 0.0
    # t = avg / standard error. |t|>~2 => distinguishable from zero at ~95%.
    # Returns are non-normal (capped by TP/SL), so treat this as a rough gauge.
    t_stat = (avg / (std / math.sqrt(n))) if std > 0 and n > 1 else 0.0
    return dict(
        label=label,
        trades=n,
        win_rate=(df['return_pct'] > 0).mean() * 100,
        avg=avg,
        t=t_stat,
        median=df['return_pct'].median(),
        compounded=(equity.iloc[-1] - 1) * 100,
        max_dd=max_dd,
        tp=counts.get('take-profit', 0),
        sl=counts.get('stop-loss', 0),
        mh=counts.get('max-hold', 0),
        exp=counts.get('expiry', 0),
        _df=df,
    )


# ----------------------------- data --------------------------------

def fetch_history(symbol, interval=INTERVAL, days_back=DAYS_BACK):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = os.path.join(CACHE_DIR, f"{symbol}_{interval}_{days_back}_{datetime.now():%Y%m%d}.pkl")
    if os.path.exists(key):
        with open(key, "rb") as f:
            return pickle.load(f)

    df = yf.download(symbol, period=f"{days_back}d", interval=interval,
                     progress=False, threads=False, auto_adjust=False)
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        df = df[['open', 'high', 'low', 'close', 'volume']].dropna()
        with open(key, "wb") as f:
            pickle.dump(df, f)
    return df


def load_all(symbols=SYMBOLS):
    """Fetch + add indicators once per symbol. Returns {symbol: df_with_indicators}."""
    data = {}
    for symbol in symbols:
        print(f"📥 {symbol} ...", end=" ", flush=True)
        df = fetch_history(symbol)
        if df.empty or len(df) < 80:
            print(f"skipped ({len(df)} bars).")
            continue
        data[symbol] = add_all_indicators(df)
        print(f"{len(df)} bars.")
    return data


# ----------------------------- sweep -------------------------------

# Each config is a name + the parameter overrides to test against the baseline.
CONFIGS = [
    ("thr 2.00", dict(signal_threshold=2.00)),
    ("thr 2.50 (baseline)", dict(signal_threshold=2.50)),
    ("thr 2.75", dict(signal_threshold=2.75)),
    ("thr 3.00", dict(signal_threshold=3.00)),
    ("thr 3.25", dict(signal_threshold=3.25)),
    ("thr 3.50", dict(signal_threshold=3.50)),
    ("thr 4.00", dict(signal_threshold=4.00)),
]


def run_sweep(data, base=Params()):
    rows = []
    for label, overrides in CONFIGS:
        p = replace(base, **overrides)
        trades = []
        for symbol, df_ind in data.items():
            trades.extend(run_backtest_on_frame(df_ind, symbol, p))
        rows.append(compute_metrics(trades, p, label))

    print("\n" + "=" * 94)
    print("THRESHOLD LADDER  (* = avg distinguishable from zero, |t|>=2)")
    print("=" * 94)
    print(f"{'config':<22}{'n':>5}{'win%':>7}{'avg%':>8}{'t':>7}{'med%':>8}{'comp%':>9}{'maxDD%':>9}{'TP/SL/MH':>13}")
    print("-" * 94)
    for r in rows:
        if not r['trades']:
            print(f"{r['label']:<22}{0:>5}   (no trades)")
            continue
        tpslmh = f"{r['tp']}/{r['sl']}/{r['mh']}"
        flag = " *" if abs(r['t']) >= 2 else ""
        print(f"{r['label']:<22}{r['trades']:>5}{r['win_rate']:>7.1f}{r['avg']:>8.2f}"
              f"{r['t']:>7.2f}{r['median']:>8.2f}{r['compounded']:>9.1f}{r['max_dd']:>9.1f}{tpslmh:>13}{flag}")
    print("=" * 94)
    print(f"(sizing: {base.risk_per_trade:.0%} of equity per trade | comp% & maxDD% reflect that)")
    return rows


def main():
    data = load_all()
    if not data:
        print("No data loaded.")
        return
    run_sweep(data)


if __name__ == "__main__":
    main()