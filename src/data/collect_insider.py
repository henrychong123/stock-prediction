"""
Insider Trading Collector — downloads insider transaction history for all US stocks.

Data source: Finnhub stock_insider_transactions()
Rate limit: 60 req/min free tier

Usage:
    python src/data/collect_insider.py                  # all US stocks
    python src/data/collect_insider.py --symbol AAPL    # specific stock
"""

import sys
import os
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import init_db, save_insider_batch
from src.data_sources.insider import fetch_insider_transactions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run(symbol: str = None):
    init_db()

    if symbol:
        symbols = [symbol]
    else:
        try:
            from config.stock_universe import get_sp500
            symbols = [s["symbol"] for s in get_sp500()]
        except ImportError:
            log.error("Could not load stock universe")
            return

    total = len(symbols)
    log.info(f"Collecting insider transactions for {total} stocks...")

    ok = 0
    total_rows = 0
    for i, sym in enumerate(symbols, 1):
        log.info(f"Processing {i}/{total}: {sym}")

        transactions = fetch_insider_transactions(sym, months_back=24)
        if transactions:
            save_insider_batch(transactions)
            ok += 1
            total_rows += len(transactions)
            log.info(f"  {sym}: {len(transactions)} transactions saved")
        else:
            log.info(f"  {sym}: no insider data")

        # Rate limit: ~1 req/sec to stay under 60/min
        if i % 50 == 0:
            log.info(f"  Progress: {i}/{total} ({ok} with data, {total_rows} rows)")
        time.sleep(1.1)

    log.info(f"\nDone — {ok}/{total} stocks with insider data, {total_rows} total transactions")


if __name__ == "__main__":
    args = sys.argv[1:]
    sym = None
    for i, a in enumerate(args):
        if a == "--symbol" and i + 1 < len(args):
            sym = args[i + 1]
    run(symbol=sym)
