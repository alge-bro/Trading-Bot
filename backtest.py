#backtest.py
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from indicators import add_all_indicators, get_trade_signal
from options_data import pick_option, pick_put_option
from sell_checker import simulate_sell

# === Config ===
SYMBOLS = ['AAPL', 'SOFI', 'SFY', 'SFYX', 'PLTR', 'NFLX', 'NVDA', 'SPY']
INTERVAL = "5m"
DAYS_BACK = 30

end_date = datetime.now()
start_date = end_date - timedelta(days=DAYS_BACK)

all_trades = []

for symbol in SYMBOLS:
    print(f"\n📊 Running backtest for {symbol}")

    data = yf.download(
        tickers=symbol,
        start=start_date.strftime('%Y-%m-%d'),
        end=end_date.strftime('%Y-%m-%d'),
        interval=INTERVAL,
        progress=False
    )

    # Fix column names (handle MultiIndex from yfinance)
    data.columns = ['_'.join(col).lower() if isinstance(col, tuple) else col.lower() for col in data.columns]
    suffix = f"_{symbol.lower()}"
    rename_map = {
        f'open{suffix}': 'open',
        f'high{suffix}': 'high',
        f'low{suffix}': 'low',
        f'close{suffix}': 'close',
        f'volume{suffix}': 'volume'
    }
    data = data.rename(columns={k: v for k, v in rename_map.items() if k in data.columns})

    if data.empty:
        print("❌ No data fetched.")
        continue

    data.columns = [col.lower() for col in data.columns]
    required_cols = ['close', 'open', 'high', 'low']
    missing = [col for col in required_cols if col not in data.columns]
    if missing:
        print(f"🚫 Missing required columns: {missing}")
        continue

    trades = []
    open_trade = None

    for i in range(50, len(data)):
        current = data.iloc[:i].copy()
        current = add_all_indicators(current)
        signal = get_trade_signal(current)
        latest = current.iloc[-1]
        timestamp = current.index[-1]

        print(f"⏱️ {timestamp} | {symbol} Close: ${latest['close']:.2f} | Signal: {signal}")

        if open_trade is None:
            if signal == "BUY_CALL":
                option = pick_option(symbol, latest['close'])
                trade_type = "CALL"
            elif signal == "BUY_PUT":
                option = pick_put_option(symbol, latest['close'])
                trade_type = "PUT"
            else:
                option = None

            if option:
                open_trade = {
                    'symbol': symbol,
                    'entry_time': timestamp,
                    'entry_price': option['last_price'],
                    'contract': option['contract'],
                    'type': trade_type
                }
                print(f"🟢 Simulated BUY ({trade_type}): {option['contract']} @ ${option['last_price']:.2f}")

        elif open_trade and open_trade['symbol'] == symbol:
            new_option = (
                pick_option(symbol, latest['close']) if open_trade['type'] == 'CALL'
                else pick_put_option(symbol, latest['close'])
            )
            if new_option:
                should_sell = simulate_sell(open_trade['entry_price'], new_option['last_price'])
                if should_sell:
                    open_trade['exit_time'] = timestamp
                    open_trade['exit_price'] = new_option['last_price']
                    open_trade['return_pct'] = round(
                        (open_trade['exit_price'] - open_trade['entry_price']) / open_trade['entry_price'] * 100, 2
                    )
                    trades.append(open_trade)
                    print(f"🔴 Simulated SELL ({open_trade['type']}): {open_trade['contract']} @ ${open_trade['exit_price']:.2f} | Return: {open_trade['return_pct']}%")
                    open_trade = None

    if trades:
        df = pd.DataFrame(trades)
        print(df[['symbol', 'type', 'entry_time', 'exit_time', 'entry_price', 'exit_price', 'return_pct', 'contract']])
        all_trades.extend(trades)
    else:
        print(f"📉 No trades completed for {symbol}.")

# === Overall Results ===
print("\n📊 Overall Backtest Summary:")

if all_trades:
    df_all = pd.DataFrame(all_trades)
    print(df_all[['symbol', 'type', 'entry_time', 'exit_time', 'entry_price', 'exit_price', 'return_pct', 'contract']])

    total_return = df_all['return_pct'].sum()
    win_rate = (df_all['return_pct'] > 0).mean() * 100
    avg_return = df_all['return_pct'].mean()

    print(f"\n✅ Total Trades: {len(df_all)}")
    print(f"✅ Win Rate: {win_rate:.2f}%")
    print(f"✅ Total Return: {total_return:.2f}%")
    print(f"✅ Avg Return per Trade: {avg_return:.2f}%")

    # Bonus breakdown
    calls = df_all[df_all['type'] == 'CALL']
    puts = df_all[df_all['type'] == 'PUT']

    print(f"\n📈 Call Win Rate: {(calls['return_pct'] > 0).mean() * 100:.2f}% ({len(calls)} trades)")
    print(f"📉 Put Win Rate: {(puts['return_pct'] > 0).mean() * 100:.2f}% ({len(puts)} trades)")
else:
    print("📉 No trades completed across all symbols.")
