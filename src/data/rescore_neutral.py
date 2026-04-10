"""
Rescore Neutral Headlines — uses Ollama LLM to re-classify headlines
that FinBERT incorrectly marked as neutral.

FinBERT misclassifies ~48% of headlines as neutral. Ollama Phi-3 Mini
is much better at understanding headline context.

Usage:
    python src/data/rescore_neutral.py              # rescore all neutral
    python src/data/rescore_neutral.py --limit 100  # rescore 100 at a time
    python src/data/rescore_neutral.py --dry-run    # preview without updating
"""

import sys
import os
import sqlite3
import logging
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.analysis.llm_analyzer import analyze_headline, is_ollama_available

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Map LLM sentiment to FinBERT-compatible scores
SENTIMENT_SCORES = {
    "bullish": 0.65,
    "bearish": -0.65,
    "neutral": 0.0,
}


def run(limit: int = 0, dry_run: bool = False):
    if not is_ollama_available():
        log.error("Ollama is not running. Start Ollama first.")
        return

    conn = sqlite3.connect('data/predictions.db')

    # Get neutral headlines
    query = "SELECT id, headline FROM news WHERE sentiment_label = 'neutral' AND headline != ''"
    if limit > 0:
        query += f" ORDER BY fetched_at DESC LIMIT {limit}"
    rows = conn.execute(query).fetchall()

    log.info(f"Rescoring {len(rows)} neutral headlines with Ollama...")
    if dry_run:
        log.info("DRY RUN — no updates will be made")

    rescored = 0
    still_neutral = 0

    for i, (rid, headline) in enumerate(rows):
        result = analyze_headline(headline)
        if not result:
            continue

        llm_sentiment = result.get("sentiment", "neutral")
        if llm_sentiment == "neutral":
            still_neutral += 1
            continue

        new_score = SENTIMENT_SCORES.get(llm_sentiment, 0)
        new_label = "positive" if llm_sentiment == "bullish" else "negative"

        if not dry_run:
            conn.execute(
                "UPDATE news SET sentiment_score=?, sentiment_label=? WHERE id=?",
                (new_score, new_label, rid)
            )
            conn.commit()  # commit after EACH update to avoid holding DB lock
            rescored += 1
        else:
            log.info(f"  [{new_label:8s} {new_score:+.2f}] {headline[:70]}")
            rescored += 1

        if (i + 1) % 20 == 0:
            log.info(f"  {i+1}/{len(rows)} processed — {rescored} rescored, {still_neutral} still neutral")

        time.sleep(0.5)  # give Ollama breathing room

    if not dry_run:
        conn.commit()
    conn.close()

    log.info(f"\nDone — {rescored}/{len(rows)} rescored ({still_neutral} confirmed neutral)")


if __name__ == "__main__":
    args = sys.argv[1:]
    limit = 0
    dry_run = "--dry-run" in args

    for i, a in enumerate(args):
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])

    run(limit=limit, dry_run=dry_run)
