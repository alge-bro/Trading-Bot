# sell_checker.py
import time
from datetime import datetime
import yfinance as yf
from positions import load_positions, remove_position

# Exit thresholds (fractions of entry premium). TUNE THESE.
TAKE_PROFIT = 0.30    # +30%: lock in the win
STOP_LOSS = -0.50     # -50%: cut the loser before theta finishes the job
MAX_HOLD_HOURS = 6    # time-based exit so nothing rots overnight


def get_option_price(contract_symbol, retries=3, delay=1):
    """Last traded price for an option contract via yfinance.
    The retry now wraps the call that actually touches the network
    (.history) — the old version retried yf.Ticker(), which never fails,
    so it was guarding the wrong line."""
    for attempt in range(retries):
        try:
            hist = yf.Ticker(contract_symbol).history(period="1d", interval="1m")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
            return None  # valid contract, just no prints today
        except Exception as e:
            print(f"[{contract_symbol}] price fetch retry {attempt + 1}/{retries}: {e}")
            time.sleep(delay)
    return None


def _exit_reason(pos, current_price):
    pnl = (current_price - pos['entry_price']) / pos['entry_price']
    if pnl >= TAKE_PROFIT:
        return "take-profit", pnl
    if pnl <= STOP_LOSS:
        return "stop-loss", pnl
    entry_time = pos.get('entry_time')
    if entry_time:
        try:
            t0 = datetime.fromisoformat(entry_time)
            held_hours = (datetime.now(t0.tzinfo) - t0).total_seconds() / 3600
            if held_hours >= MAX_HOLD_HOURS:
                return "max-hold", pnl
        except ValueError:
            pass
    return None, pnl


def check_for_sell_opportunities(send_sms, log_trade):
    """Alert + bookkeeping only — like execute_trade, this does not submit a
    real closing order. Place the broker sell HERE before remove_position()
    if you go live."""
    positions = load_positions()

    for symbol, pos in list(positions.items()):  # list() so we can mutate as we go
        current_price = get_option_price(pos['contract'])
        if current_price is None:
            continue

        reason, pnl = _exit_reason(pos, current_price)
        if reason:
            message = (f"💵 SELL {symbol} ({reason}):\n"
                       f"📈 Bought ${pos['entry_price']:.2f} → Now ${current_price:.2f} "
                       f"({pnl * 100:+.1f}%)\n"
                       f"📝 {pos['contract']}")
            send_sms(message)
            log_trade(symbol, f"SELL ({pos['contract']}) [{reason}]", current_price)
            remove_position(symbol)


def simulate_sell(entry_price, current_price):
    """Used by the backtest. Now respects both the profit target and the
    stop-loss, matching live behavior."""
    if entry_price is None or current_price is None:
        return False
    pnl = (current_price - entry_price) / entry_price
    return pnl >= TAKE_PROFIT or pnl <= STOP_LOSS