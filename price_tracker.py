"""
Price Tracker — polls Bursa Malaysia (and US) stock prices and stores
snapshots to SQLite for prediction accuracy tracking.

Run via Task Scheduler every 5 minutes during market hours:
  XHS-PriceTracker  →  wscript.exe run_hidden.vbs price_tracker.py
  Schedule: Mon–Fri, repeat every 5 min from 09:00 to 17:05 (MYT)

Can also be triggered manually:
  .venv\Scripts\python.exe price_tracker.py
  .venv\Scripts\python.exe price_tracker.py --force   # skip market hours check
"""

import sys
import json
from datetime import datetime, time
from zoneinfo import ZoneInfo

import logging

import yfinance as yf

sys.path.insert(0, ".")
from src.database import (
    save_price_snapshot, get_tracked_symbols, get_connection, init_db
)
from config.settings import MARKETS, DEFAULT_SYMBOLS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [price_tracker] %(levelname)s %(message)s",
)
log = logging.getLogger("price_tracker")

MYT = ZoneInfo("Asia/Kuala_Lumpur")
ET  = ZoneInfo("America/New_York")


# ── Market hours helpers ─────────────────────────────────────────────────────

def _bursa_open(now_myt: datetime) -> bool:
    if now_myt.weekday() >= 5:
        return False
    t = now_myt.time()
    return time(9, 0) <= t <= time(12, 30) or time(14, 30) <= t <= time(17, 5)


def _us_open(now_et: datetime) -> bool:
    if now_et.weekday() >= 5:
        return False
    t = now_et.time()
    return time(9, 30) <= t <= time(16, 5)


def should_poll(force: bool = False) -> bool:
    if force:
        return True
    now_myt = datetime.now(MYT)
    now_et  = datetime.now(ET)
    return _bursa_open(now_myt) or _us_open(now_et)


# ── Symbol collection ────────────────────────────────────────────────────────

def _symbols_to_poll() -> list[str]:
    """
    Collect all symbols worth polling:
    1. MY default watchlist + KLCI index
    2. US default watchlist + S&P 500
    3. Any symbol that has ever been predicted (stored in predictions table)
    """
    symbols: set[str] = set()

    # MY watchlist
    symbols.update(MARKETS["MY"]["default_symbols"])
    symbols.add(MARKETS["MY"]["index"])   # ^KLSE

    # US watchlist
    symbols.update(MARKETS["US"]["default_symbols"])
    symbols.add(MARKETS["US"]["index"])   # ^GSPC

    # Symbols with predictions in DB (so accuracy tracking works for any symbol
    # the user has ever run a prediction on)
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM predictions"
        ).fetchall()
        conn.close()
        for r in rows:
            symbols.add(r["symbol"])
    except Exception as e:
        log.warning("Could not read prediction symbols: %s", e)

    return sorted(symbols)


# ── Core polling ─────────────────────────────────────────────────────────────

def _fetch_and_store(symbol: str) -> bool:
    """Fetch fast_info for one symbol and write a snapshot. Returns True on success."""
    try:
        t = yf.Ticker(symbol)
        fi = t.fast_info

        price = fi.last_price
        if not price:
            return False

        prev_close = fi.previous_close
        change_abs = round(price - prev_close, 4) if prev_close else None
        change_pct = round(change_abs / prev_close * 100, 4) if prev_close else None

        save_price_snapshot(
            symbol=symbol,
            price=round(price, 4),
            prev_close=round(prev_close, 4) if prev_close else None,
            change_abs=change_abs,
            change_pct=change_pct,
            volume=int(fi.last_volume) if fi.last_volume else None,
            bid=round(fi.bid, 4) if hasattr(fi, "bid") and fi.bid else None,
            ask=round(fi.ask, 4) if hasattr(fi, "ask") and fi.ask else None,
            day_high=round(fi.day_high, 4) if fi.day_high else None,
            day_low=round(fi.day_low, 4) if fi.day_low else None,
        )
        return True
    except Exception as e:
        log.warning("Failed to fetch %s: %s", symbol, e)
        return False


def run(force: bool = False):
    init_db()

    if not should_poll(force):
        log.info("Market closed — skipping poll")
        return

    symbols = _symbols_to_poll()
    log.info("Polling %d symbols", len(symbols))

    ok = 0
    for sym in symbols:
        if _fetch_and_store(sym):
            ok += 1

    log.info("Snapshot complete: %d/%d succeeded", ok, len(symbols))


if __name__ == "__main__":
    force = "--force" in sys.argv
    run(force=force)
