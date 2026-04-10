"""
Bursa News Historical Backfill — collects past Bursa Malaysia headlines
from Google News RSS with date-range searches.

Goes back up to 24 months. ~30-90 articles per month.
Runs FinBERT sentiment on each headline.

Usage:
    python src/data/collect_bursa_news_history.py                  # 12 months
    python src/data/collect_bursa_news_history.py --months 24      # 24 months
    python src/data/collect_bursa_news_history.py --skip-sentiment  # fast (no NLP)
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import feedparser
from src.database import init_db, save_news

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Search queries to cover different Bursa topics
SEARCH_QUERIES = [
    "Bursa+Malaysia+stock",
    "KLSE+market",
    "Maybank+CIMB+bank+Malaysia",
    "Petronas+oil+gas+Malaysia",
    "palm+oil+plantation+Malaysia",
    "Tenaga+utilities+Malaysia",
    "Malaysia+economy+ringgit",
    "Bursa+IPO+listing",
    "KLCI+index+market",
    "Genting+gaming+Malaysia",
]

_sentiment_pipeline = None


def _get_sentiment(headline: str) -> tuple[str, float]:
    """Run FinBERT on a headline."""
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        try:
            from src.data_sources.news_sentiment import _get_sentiment_pipeline
            _sentiment_pipeline = _get_sentiment_pipeline()
        except Exception:
            return "neutral", 0.0

    if not _sentiment_pipeline:
        return "neutral", 0.0

    try:
        result = _sentiment_pipeline(headline[:512])
        top = result[0] if isinstance(result[0], dict) else result[0][0]
        label = top["label"].lower()
        score = top["score"]
        if label == "positive":
            return "positive", round(score, 4)
        elif label == "negative":
            return "negative", round(-score, 4)
        return "neutral", 0.0
    except Exception:
        return "neutral", 0.0


def collect_month(year: int, month: int, run_sentiment: bool = True) -> int:
    """Collect Bursa news for a specific month from Google News RSS."""
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"

    saved = 0
    seen_titles = set()

    for query in SEARCH_QUERIES:
        url = (f"https://news.google.com/rss/search?"
               f"q={query}+after:{start}+before:{end}"
               f"&hl=en-MY&gl=MY&ceid=MY:en")

        try:
            feed = feedparser.parse(url)
        except Exception:
            continue

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            if not title or len(title) < 15:
                continue

            title_key = title.lower()[:50]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            # Parse date
            published = ""
            if entry.get("published_parsed"):
                try:
                    published = datetime(*entry.published_parsed[:6]).isoformat()
                except Exception:
                    pass

            sent_label, sent_score = "", 0.0
            if run_sentiment:
                sent_label, sent_score = _get_sentiment(title)

            try:
                save_news(
                    platform="google-news-my",
                    headline=title,
                    summary=entry.get("summary", "")[:200],
                    url=entry.get("link", ""),
                    source_name="Google News MY",
                    sentiment_label=sent_label,
                    sentiment_score=sent_score,
                    related_symbol="",
                )
                saved += 1
            except Exception:
                pass

        time.sleep(1)  # rate limit between queries

    return saved


def run(months_back: int = 12, skip_sentiment: bool = False):
    init_db()
    run_sentiment = not skip_sentiment

    if run_sentiment:
        log.info("Pre-loading FinBERT...")
        _get_sentiment("test")
        log.info("FinBERT ready.")

    now = datetime.now()
    total_saved = 0

    log.info(f"Backfilling {months_back} months of Bursa news from Google News...")

    for i in range(months_back):
        target = now - timedelta(days=30 * i)
        year, month = target.year, target.month
        label = f"{year}-{month:02d}"

        saved = collect_month(year, month, run_sentiment=run_sentiment)
        total_saved += saved
        log.info(f"  {label}: {saved} articles saved")

    log.info(f"\nDone — {total_saved} Bursa articles backfilled across {months_back} months")


if __name__ == "__main__":
    args = sys.argv[1:]
    months = 12
    skip_sent = "--skip-sentiment" in args

    for i, a in enumerate(args):
        if a == "--months" and i + 1 < len(args):
            months = int(args[i + 1])

    run(months_back=months, skip_sentiment=skip_sent)
