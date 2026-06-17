# positions.py
# Single source of truth for open option positions.
# Previously load/save_positions lived in BOTH options_data.py and
# sell_checker.py (two copies, easy to drift). Now everyone imports from here.

import os
import json
import threading
from datetime import datetime

POSITIONS_FILE = "positions.json"
_lock = threading.Lock()


def load_positions():
    if not os.path.exists(POSITIONS_FILE):
        return {}
    try:
        with open(POSITIONS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # A corrupt/half-written file should not crash the bot.
        print("⚠️ positions.json unreadable — starting from empty.")
        return {}


def save_positions(positions):
    # Atomic write: dump to a temp file, then replace. Prevents a crash
    # mid-write from leaving you with a corrupted positions.json.
    with _lock:
        tmp = POSITIONS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(positions, f, indent=4)
        os.replace(tmp, POSITIONS_FILE)


def has_open_position(symbol):
    return symbol in load_positions()


def add_position(symbol, option_data, trade_type):
    """Record a newly opened position so the sell-checker can later find it."""
    positions = load_positions()
    positions[symbol] = {
        "contract": option_data["contract"],
        "type": trade_type,                       # "CALL" or "PUT"
        "strike": option_data.get("strike"),
        "expiration": option_data.get("expiration"),
        "entry_price": option_data["last_price"],  # the mid we "filled" at
        "entry_time": datetime.now().astimezone().isoformat(),
    }
    save_positions(positions)
    return positions[symbol]


def remove_position(symbol):
    positions = load_positions()
    positions.pop(symbol, None)
    save_positions(positions)
    return positions