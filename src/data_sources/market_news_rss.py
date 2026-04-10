"""
Market News RSS Crawler — fetches headlines from Benzinga, MarketWatch,
and other free financial RSS feeds.

Free, no API keys needed. Good for broad market sentiment and catalyst detection.

Usage:
    from src.data_sources.market_news_rss import fetch_all_rss_news
    articles = fetch_all_rss_news()
"""

import logging
from datetime import datetime

import feedparser

log = logging.getLogger(__name__)

# RSS feeds to crawl
RSS_FEEDS = {
    # ── US / Global ──────────────────────────────────────────────
    "benzinga": {
        "url": "https://www.benzinga.com/feed",
        "platform": "benzinga",
    },
    "marketwatch": {
        "url": "https://feeds.marketwatch.com/marketwatch/topstories",
        "platform": "marketwatch",
    },
    "marketwatch-stocks": {
        "url": "https://feeds.marketwatch.com/marketwatch/StockstoWatch",
        "platform": "marketwatch",
    },
    "cnbc": {
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
        "platform": "cnbc",
    },
    "reuters-business": {
        "url": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
        "platform": "reuters",
    },
    "investing-news": {
        "url": "https://www.investing.com/rss/news.rss",
        "platform": "investing",
    },
    # ── Malaysia / Bursa ─────────────────────────────────────────
    "google-news-bursa": {
        "url": "https://news.google.com/rss/search?q=Bursa+Malaysia+stock&hl=en-MY&gl=MY&ceid=MY:en",
        "platform": "google-news-my",
    },
    "google-news-klse": {
        "url": "https://news.google.com/rss/search?q=KLSE+saham+Bursa&hl=ms-MY&gl=MY&ceid=MY:ms",
        "platform": "google-news-my",
    },
    "fmt-business": {
        "url": "https://www.freemalaysiatoday.com/category/business/feed/",
        "platform": "fmt",
    },
    "malaymail-money": {
        "url": "https://www.malaymail.com/feed/rss/money",
        "platform": "malaymail",
    },
}


def _parse_feed(name: str, config: dict) -> list[dict]:
    """Parse a single RSS feed and return article dicts."""
    try:
        feed = feedparser.parse(config["url"])
        articles = []

        for entry in feed.entries[:20]:  # max 20 per feed
            title = entry.get("title", "").strip()
            if not title or len(title) < 10:
                continue

            # Parse published date
            published = ""
            if entry.get("published_parsed"):
                try:
                    published = datetime(*entry.published_parsed[:6]).isoformat()
                except Exception:
                    pass

            summary = entry.get("summary", "")
            # Strip HTML tags from summary
            if "<" in summary:
                import re
                summary = re.sub(r"<[^>]+>", "", summary).strip()
            summary = summary[:300]  # cap length

            articles.append({
                "headline": title,
                "summary": summary,
                "url": entry.get("link", ""),
                "source_name": config["platform"].title(),
                "source_platform": config["platform"],
                "related_symbol": "",
                "fetched_at": datetime.now().isoformat(),
                "published_at": published,
            })

        return articles
    except Exception as e:
        log.warning(f"RSS feed {name} failed: {e}")
        return []


def fetch_all_rss_news() -> list[dict]:
    """Fetch headlines from all configured RSS feeds.

    Returns deduplicated list of articles sorted by publish time.
    """
    all_articles = []
    seen_titles = set()

    for name, config in RSS_FEEDS.items():
        articles = _parse_feed(name, config)
        for a in articles:
            # Deduplicate by title
            title_key = a["headline"].lower()[:60]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                all_articles.append(a)

        log.info(f"  {name}: {len(articles)} articles")

    # Sort by publish time (newest first)
    all_articles.sort(key=lambda a: a.get("published_at", ""), reverse=True)

    log.info(f"Total RSS articles: {len(all_articles)} (from {len(RSS_FEEDS)} feeds)")
    return all_articles
