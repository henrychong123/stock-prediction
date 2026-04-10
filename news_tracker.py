"""
News Tracker — continuously polls news sources and stores articles to SQLite.

Two-tier polling strategy respects free API rate limits:
  FAST sources (RSS, no quota)  — polled every run  (~30 min via Task Scheduler)
  SLOW sources (keyed APIs)     — polled every 2 hrs (tracked in news_tracker_state)

Run via Task Scheduler every 30 minutes:
  StockPred-NewsTracker  →  wscript.exe run_hidden.vbs news_tracker.py
  Schedule: Daily, repeat every 30 min from 07:00 to 23:30

Can also be triggered manually:
  .venv\Scripts\python.exe news_tracker.py
  .venv\Scripts\python.exe news_tracker.py --force   # force slow-tier sources too
"""

import sys
import logging
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from src.database import (
    init_db, save_news,
    get_tracker_last_fetched, set_tracker_last_fetched,
)
from src.data_sources.news_sentiment import analyze_sentiment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [news_tracker] %(levelname)s %(message)s",
)
log = logging.getLogger("news_tracker")

# Minimum gap between slow-source fetches (rate-limited APIs)
SLOW_INTERVAL_HOURS = 2


def _should_fetch_slow(source: str, force: bool) -> bool:
    if force:
        return True
    last = get_tracker_last_fetched(source)
    if last is None:
        return True
    # last_fetched stored as UTC naive in SQLite
    now = datetime.utcnow()
    if last.tzinfo is not None:
        last = last.replace(tzinfo=None)
    return (now - last) >= timedelta(hours=SLOW_INTERVAL_HOURS)


# ── Fast sources (RSS — no API key, no quota) ─────────────────────────────────

def _fetch_fast() -> int:
    """Fetch Google News RSS + The Edge Markets RSS. Returns saved count."""
    saved = 0
    try:
        from src.data_sources.news_my import fetch_google_news_my, fetch_edge_markets_news
        for fn, label in [(fetch_google_news_my, "google-news-my"),
                          (fetch_edge_markets_news, "edge-markets")]:
            try:
                articles = fn()
                for a in articles:
                    save_news(
                        platform=a.get("platform", label),
                        headline=a.get("headline", ""),
                        summary=a.get("summary", ""),
                        url=a.get("url", ""),
                        source_name=a.get("source", ""),
                        sentiment_label=a.get("sentiment", {}).get("label", ""),
                        sentiment_score=a.get("sentiment", {}).get("score", 0),
                    )
                    saved += 1
                log.info("  %s: %d articles", label, len(articles))
            except Exception as e:
                log.warning("  %s failed: %s", label, e)
    except ImportError as e:
        log.warning("Could not import fast sources: %s", e)
    return saved


# ── Slow sources (API keys, rate-limited) ─────────────────────────────────────

def _fetch_finnhub(force: bool) -> int:
    if not _should_fetch_slow("finnhub", force):
        log.info("  finnhub: skipped (fetched < %dh ago)", SLOW_INTERVAL_HOURS)
        return 0
    saved = 0
    try:
        from src.data_sources.news_sentiment import (
            fetch_market_news, fetch_influential_figure_news
        )
        for fn, label in [(fetch_market_news, "finnhub"),
                          (fetch_influential_figure_news, "finnhub-figures")]:
            try:
                articles = fn() if fn == fetch_market_news else fn()
                for a in articles:
                    if "error" in a:
                        continue
                    save_news(
                        platform=label,
                        headline=a.get("headline", ""),
                        summary=a.get("summary", ""),
                        url=a.get("url", ""),
                        source_name=a.get("source", ""),
                        sentiment_label=a.get("sentiment", {}).get("label", ""),
                        sentiment_score=a.get("sentiment", {}).get("score", 0),
                        related_figure=a.get("figure", ""),
                    )
                    saved += 1
                log.info("  %s: %d articles", label, len(articles))
            except Exception as e:
                log.warning("  %s failed: %s", label, e)
        set_tracker_last_fetched("finnhub")
    except ImportError as e:
        log.warning("Could not import finnhub sources: %s", e)
    return saved


def _fetch_newsapi(force: bool) -> int:
    if not _should_fetch_slow("newsapi", force):
        log.info("  newsapi: skipped (fetched < %dh ago)", SLOW_INTERVAL_HOURS)
        return 0
    saved = 0
    try:
        from src.data_sources.news_my import fetch_newsapi_my
        articles = fetch_newsapi_my()
        for a in articles:
            save_news(
                platform=a.get("platform", "newsapi"),
                headline=a.get("headline", ""),
                summary=a.get("summary", ""),
                url=a.get("url", ""),
                source_name=a.get("source", ""),
                sentiment_label=a.get("sentiment", {}).get("label", ""),
                sentiment_score=a.get("sentiment", {}).get("score", 0),
            )
            saved += 1
        log.info("  newsapi: %d articles", len(articles))
        if articles:
            set_tracker_last_fetched("newsapi")
    except Exception as e:
        log.warning("  newsapi failed: %s", e)
    return saved


def _fetch_my_influential(force: bool) -> int:
    if not _should_fetch_slow("my-influential", force):
        log.info("  my-influential: skipped (fetched < %dh ago)", SLOW_INTERVAL_HOURS)
        return 0
    saved = 0
    try:
        from src.data_sources.news_my import fetch_my_influential_news
        articles = fetch_my_influential_news()
        for a in articles:
            save_news(
                platform="google-news-my",
                headline=a.get("headline", ""),
                summary=a.get("summary", ""),
                url=a.get("url", ""),
                source_name=a.get("source", ""),
                sentiment_label=a.get("sentiment", {}).get("label", ""),
                sentiment_score=a.get("sentiment", {}).get("score", 0),
                related_figure=a.get("figure", ""),
            )
            saved += 1
        log.info("  my-influential: %d articles", len(articles))
        set_tracker_last_fetched("my-influential")
    except Exception as e:
        log.warning("  my-influential failed: %s", e)
    return saved


# ── Main ──────────────────────────────────────────────────────────────────────

def run(force: bool = False):
    init_db()
    log.info("News tracker run started (force=%s)", force)

    total = 0

    # Fast tier — always run
    log.info("Fast tier (RSS):")
    total += _fetch_fast()

    # Slow tier — rate-limited APIs
    log.info("Slow tier (APIs):")
    total += _fetch_finnhub(force)
    total += _fetch_newsapi(force)
    total += _fetch_my_influential(force)

    log.info("Done — %d articles saved/attempted", total)


if __name__ == "__main__":
    force = "--force" in sys.argv
    run(force=force)
