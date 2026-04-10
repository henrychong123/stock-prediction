"""
Batch Prediction Runner — runs predictions for all Bursa stocks (and optionally US).

Saves results to the existing predictions table. Schedule daily after market close.

Usage:
    python src/data/batch_predict.py              # all 80 Bursa stocks
    python src/data/batch_predict.py --us          # include US stocks too
    python src/data/batch_predict.py --quick       # technical-only (skip news/social, much faster)
"""

import sys
import os
import time
import logging
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import init_db
from config.settings import BURSA_INDUSTRIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

US_STOCKS = ["TSLA", "AAPL", "NVDA", "GOOGL", "AMZN", "MSFT", "META", "SPY", "QQQ", "DIA"]


def get_bursa_symbols() -> list[tuple[str, str]]:
    """Return list of (symbol, name) for all Bursa stocks."""
    result = []
    for ind in BURSA_INDUSTRIES.values():
        for s in ind["stocks"]:
            result.append((s["symbol"], s["name"]))
    return result


def run(include_us=False, quick=False):
    init_db()
    from src.analysis.predictor import predict

    stocks = get_bursa_symbols()
    if include_us:
        stocks += [(s, s) for s in US_STOCKS]

    total = len(stocks)
    log.info(f"Running batch predictions for {total} stocks...")
    if quick:
        log.info("Quick mode: technical indicators only (skipping news/social)")

    ok = 0
    failed = 0
    results = []

    for i, (symbol, name) in enumerate(stocks, 1):
        log.info(f"[{i}/{total}] {symbol} ({name})...")
        try:
            result = predict(symbol, fast=quick)  # --quick uses fast mode, default uses full
            ok += 1
            results.append({
                "symbol": symbol,
                "name": name,
                "action": result.action,
                "confidence": result.confidence,
            })
            log.info(f"  -> {result.action} (confidence: {result.confidence:.1%})")
        except Exception as e:
            failed += 1
            log.warning(f"  -> FAILED: {e}")

        # Rate limit friendliness
        if i % 5 == 0:
            time.sleep(2)

    # Summary
    log.info(f"\n{'='*50}")
    log.info(f"BATCH PREDICTION COMPLETE")
    log.info(f"{'='*50}")
    log.info(f"  Success: {ok}/{total}")
    log.info(f"  Failed:  {failed}/{total}")
    log.info(f"  Time:    {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Print action distribution
    from collections import Counter
    actions = Counter(r["action"] for r in results)
    for action, count in actions.most_common():
        log.info(f"  {action}: {count} stocks")


if __name__ == "__main__":
    args = sys.argv[1:]
    include_us = "--us" in args
    quick = "--quick" in args
    run(include_us=include_us, quick=quick)
