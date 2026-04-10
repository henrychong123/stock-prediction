"""
Historical Earnings Collector — downloads EPS actual vs estimate data
for all US stocks via Finnhub API.

Collects up to 16 quarters (~4 years) of earnings history per stock.
Stores in earnings_history table for ML training features.

Usage:
    python src/data/collect_earnings.py                    # all US stocks
    python src/data/collect_earnings.py --symbol AAPL      # specific stock
    python src/data/collect_earnings.py --limit 8          # last 8 quarters
"""

import sys
import os
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import init_db, save_earnings_batch
from src.data_sources.earnings import fetch_company_earnings
from config.settings import FINNHUB_API_KEY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def collect_stock_earnings(symbol: str, limit: int = 16) -> int:
    """Collect earnings history for one stock. Returns count of records saved."""
    history = fetch_company_earnings(symbol, limit=limit)
    if not history or (history and "error" in history[0]):
        return 0

    batch = []
    for item in history:
        eps_actual = item.get("eps_actual")
        eps_estimate = item.get("eps_estimate")
        surprise_pct = item.get("surprise_pct")

        batch.append({
            "symbol": symbol,
            "date": item.get("date", item.get("period", "")),
            "period": item.get("period", ""),
            "eps_actual": eps_actual,
            "eps_estimate": eps_estimate,
            "surprise_pct": surprise_pct,
            "revenue_actual": None,
            "revenue_estimate": None,
            "revenue_surprise_pct": None,
        })

    if batch:
        save_earnings_batch(batch)

    return len(batch)


def run(symbol_filter: str = None, limit: int = 16):
    """Collect earnings for all US stocks or a specific symbol."""
    if not FINNHUB_API_KEY:
        log.error("FINNHUB_API_KEY not set. Get one free at https://finnhub.io/register")
        return

    init_db()

    if symbol_filter:
        symbols = [symbol_filter.upper()]
    else:
        # Get all US stocks from stock universe
        try:
            from config.stock_universe import get_all_stocks
            all_stocks = get_all_stocks()
            symbols = [s["symbol"] for s in all_stocks
                       if s["market"] == "US" and not s["symbol"].startswith("^")]
        except ImportError:
            from src.data.collect_historical import US_STOCKS
            symbols = US_STOCKS

    total = len(symbols)
    total_saved = 0
    errors = 0

    log.info(f"Earnings Collection")
    log.info(f"  Stocks: {total}")
    log.info(f"  Quarters per stock: {limit}")
    log.info("")

    for i, sym in enumerate(symbols, 1):
        try:
            count = collect_stock_earnings(sym, limit=limit)
            total_saved += count
            if count:
                log.info(f"  [{i}/{total}] {sym}: {count} quarters")
            else:
                log.info(f"  [{i}/{total}] {sym}: no data")
        except Exception as e:
            log.warning(f"  [{i}/{total}] {sym}: error — {e}")
            errors += 1

        # Respect Finnhub rate limits (60 req/min free tier)
        time.sleep(1.2)

    log.info(f"\nDone — {total_saved} records saved, {errors} errors")


if __name__ == "__main__":
    args = sys.argv[1:]
    symbol = None
    limit = 16

    for i, a in enumerate(args):
        if a == "--symbol" and i + 1 < len(args):
            symbol = args[i + 1]
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])

    run(symbol_filter=symbol, limit=limit)
