"""
Catalyst Scanner — runs every 30 minutes to detect market-moving events
and predict which stocks will rise/fall in the next 24 hours.

Usage:
    python catalyst_scanner.py              # run once
    python catalyst_scanner.py --loop       # run every 30 minutes
    python catalyst_scanner.py --hours 12   # scan last 12 hours of news
"""

import sys
import os
import time
import logging
from datetime import datetime
import uuid

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.database import init_db, save_catalyst_scan
from src.analysis.catalyst import scan_catalysts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SCAN_INTERVAL = 30 * 60  # 30 minutes


def run_scan(hours_back: int = 6):
    """Run a single catalyst scan."""
    log.info(f"{'='*60}")
    log.info(f"Catalyst scan started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"{'='*60}")

    result = scan_catalysts(hours_back=hours_back, max_picks=10)

    events = result.get("events", [])
    picks = result.get("picks", [])

    log.info(f"\nHeadlines scanned: {result.get('headlines_scanned', 0)}")
    log.info(f"Catalyst events detected: {len(events)}")
    log.info(f"Stock picks generated: {len(picks)}")

    if events:
        log.info("\n--- CATALYST EVENTS ---")
        for e in events:
            log.info(f"  [{e['confidence']:.0%}] {e['label']}")
            log.info(f"         {e['headline'][:100]}")
            for ind, direction in e["affected_industries"].items():
                icon = "+" if direction == "bullish" else "-"
                log.info(f"         {icon} {ind} ({direction})")

    if picks:
        log.info("\n--- TOP STOCK PICKS (24h) ---")
        for i, p in enumerate(picks, 1):
            icon = "^" if p["direction"] == "bullish" else "v"
            log.info(f"  {i}. {icon} {p['symbol']:8s} {p['name'][:25]:25s} "
                     f"Score: {p['score']:5.1f}  Move: {p['predicted_move_pct']:+.1f}%  "
                     f"${p['current_price']:.2f}")
            for reason in p["reasons"]:
                log.info(f"     - {reason}")

    # Save to DB
    scan_id = str(uuid.uuid4())[:8]
    direct = result.get("direct_picks", [])
    save_catalyst_scan(scan_id, events, picks, direct_picks=direct)
    log.info(f"\nScan saved (id: {scan_id})")

    return result


def run_loop(hours_back: int = 6):
    """Run catalyst scanner in a loop every 30 minutes."""
    log.info(f"Starting catalyst scanner loop (every {SCAN_INTERVAL//60} min)...")

    while True:
        try:
            run_scan(hours_back=hours_back)
        except Exception as e:
            log.error(f"Scan failed: {e}")

        log.info(f"\nNext scan in {SCAN_INTERVAL//60} minutes...")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    init_db()

    args = sys.argv[1:]
    hours = 6
    loop = "--loop" in args

    for i, a in enumerate(args):
        if a == "--hours" and i + 1 < len(args):
            hours = int(args[i + 1])

    if loop:
        run_loop(hours_back=hours)
    else:
        run_scan(hours_back=hours)
