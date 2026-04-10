"""
Analyst Consensus Collector — downloads recommendation history for all US stocks.

Data source: Finnhub recommendation_trends()
Rate limit: 60 req/min free tier

Usage:
    python src/data/collect_analyst.py                  # all US stocks
    python src/data/collect_analyst.py --symbol AAPL    # specific stock
"""

import sys
import os
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import init_db, save_analyst_batch
from src.data_sources.analyst import fetch_recommendation_trends

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
    log.info(f"Collecting analyst recommendations for {total} stocks...")

    ok = 0
    total_rows = 0
    for i, sym in enumerate(symbols, 1):
        log.info(f"Processing {i}/{total}: {sym}")

        trends = fetch_recommendation_trends(sym)
        if trends:
            save_analyst_batch(trends)
            ok += 1
            total_rows += len(trends)
            log.info(f"  {sym}: {len(trends)} monthly records saved")
        else:
            log.info(f"  {sym}: no analyst data")

        # Rate limit: ~1 req/sec
        if i % 50 == 0:
            log.info(f"  Progress: {i}/{total} ({ok} with data, {total_rows} rows)")
        time.sleep(1.1)

    log.info(f"\nDone — {ok}/{total} stocks with analyst data, {total_rows} total records")


if __name__ == "__main__":
    args = sys.argv[1:]
    sym = None
    for i, a in enumerate(args):
        if a == "--symbol" and i + 1 < len(args):
            sym = args[i + 1]
    run(symbol=sym)
