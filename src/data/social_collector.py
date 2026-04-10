"""
Social & News Collector — aggregates headlines from multiple free sources
and saves them to the news DB table with FinBERT sentiment.

Sources:
1. Yahoo Finance News API (stock-specific, free)
2. Benzinga + MarketWatch + CNBC RSS (market-wide, free)
3. YouTube (stock-specific, requires API key — optional)

Runs every 2 hours via scheduler. All articles feed into the catalyst system.

Usage:
    python src/data/social_collector.py                    # all sources
    python src/data/social_collector.py --symbol AAPL      # specific stock
    python src/data/social_collector.py --skip-youtube      # skip YouTube
    python src/data/social_collector.py --skip-sentiment    # skip FinBERT (fast)
"""

import sys
import os
import time
import logging
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import init_db, save_news

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Core stocks to fetch stock-specific news for
CORE_SYMBOLS = [
    # US mega-caps
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "META", "JPM", "V", "AVGO",
    # Bursa blue chips
    "1155.KL", "1295.KL", "1023.KL", "5347.KL", "5183.KL", "5225.KL",
    "5285.KL", "6947.KL", "3182.KL", "8869.KL", "5681.KL", "7113.KL",
]

# FinBERT pipeline (lazy loaded)
_sentiment_pipeline = None


def _get_sentiment(headline: str) -> tuple[str, float]:
    """Run FinBERT on a headline. Returns (label, score)."""
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
        result = _sentiment_pipeline(headline[:512])[0]
        label = result["label"].lower()
        score = result["score"]
        if label == "positive":
            return "positive", round(score, 4)
        elif label == "negative":
            return "negative", round(-score, 4)
        return "neutral", 0.0
    except Exception:
        return "neutral", 0.0


def _save_articles(articles: list[dict], run_sentiment: bool = True) -> int:
    """Save articles to DB with optional FinBERT sentiment. Returns count saved."""
    saved = 0
    for article in articles:
        headline = article.get("headline", "")
        if not headline or len(headline) < 15:
            continue

        # Run sentiment if not already set
        sent_label = article.get("sentiment_label", "")
        sent_score = article.get("sentiment_score", 0)
        if run_sentiment and not sent_label:
            sent_label, sent_score = _get_sentiment(headline)

        try:
            save_news(
                platform=article.get("source_platform", "unknown"),
                headline=headline,
                summary=article.get("summary", ""),
                url=article.get("url", ""),
                source_name=article.get("source_name", ""),
                sentiment_label=sent_label,
                sentiment_score=sent_score,
                related_symbol=article.get("related_symbol", ""),
            )
            saved += 1
        except Exception:
            pass  # dedup via UNIQUE index

    return saved


def collect_rss_news(run_sentiment: bool = True) -> int:
    """Collect from all RSS feeds (Benzinga, MarketWatch, etc.)."""
    from src.data_sources.market_news_rss import fetch_all_rss_news

    log.info("Collecting RSS news (Benzinga, MarketWatch, CNBC)...")
    articles = fetch_all_rss_news()
    saved = _save_articles(articles, run_sentiment=run_sentiment)
    log.info(f"  RSS: {len(articles)} fetched, {saved} new saved")
    return saved


def collect_yahoo_news(symbols: list[str] = None, run_sentiment: bool = True) -> int:
    """Collect stock-specific news from Yahoo Finance."""
    from src.data_sources.yahoo_news import fetch_yahoo_news, fetch_yahoo_market_news

    symbols = symbols or CORE_SYMBOLS
    log.info(f"Collecting Yahoo Finance news for {len(symbols)} stocks...")

    total_saved = 0

    # Market-wide news
    market_articles = fetch_yahoo_market_news()
    total_saved += _save_articles(market_articles, run_sentiment=run_sentiment)

    # Stock-specific news
    for sym in symbols:
        articles = fetch_yahoo_news(sym, count=10)
        saved = _save_articles(articles, run_sentiment=run_sentiment)
        total_saved += saved
        if saved > 0:
            log.info(f"  {sym}: {saved} new articles")
        time.sleep(0.5)  # rate limit

    log.info(f"  Yahoo Finance: {total_saved} new articles total")
    return total_saved


def collect_youtube(symbols: list[str] = None, run_sentiment: bool = True) -> int:
    """Collect from YouTube (requires YOUTUBE_API_KEY)."""
    from src.data_sources.youtube_sentiment import fetch_youtube_sentiment

    if not os.getenv("YOUTUBE_API_KEY"):
        log.info("  YouTube: skipped (YOUTUBE_API_KEY not set)")
        return 0

    symbols = symbols or CORE_SYMBOLS[:5]  # limit to save quota
    log.info(f"Collecting YouTube sentiment for {len(symbols)} stocks...")

    total_saved = 0
    for sym in symbols:
        articles = fetch_youtube_sentiment(sym, max_videos=3)
        saved = _save_articles(articles, run_sentiment=run_sentiment)
        total_saved += saved
        if saved > 0:
            log.info(f"  {sym}: {saved} new YouTube articles")
        time.sleep(1)  # respect quota

    log.info(f"  YouTube: {total_saved} new articles total")
    return total_saved


def run(symbols: list[str] = None, skip_youtube: bool = False,
        skip_sentiment: bool = False):
    """Run the full social collection pipeline."""
    init_db()
    run_sentiment = not skip_sentiment

    log.info(f"{'='*60}")
    log.info(f"Social Collector started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"{'='*60}")

    total = 0

    # 1. RSS feeds (fastest, no rate limit)
    total += collect_rss_news(run_sentiment=run_sentiment)

    # 2. Yahoo Finance (stock-specific, light rate limit)
    total += collect_yahoo_news(symbols=symbols, run_sentiment=run_sentiment)

    # 3. YouTube (optional, quota-limited)
    if not skip_youtube:
        total += collect_youtube(symbols=symbols, run_sentiment=run_sentiment)

    log.info(f"\nDone — {total} new articles collected and saved")
    return total


if __name__ == "__main__":
    args = sys.argv[1:]
    skip_yt = "--skip-youtube" in args
    skip_sent = "--skip-sentiment" in args
    symbols = None

    for i, a in enumerate(args):
        if a == "--symbol" and i + 1 < len(args):
            symbols = [args[i + 1]]

    run(symbols=symbols, skip_youtube=skip_yt, skip_sentiment=skip_sent)
