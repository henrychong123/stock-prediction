"""
Yahoo Finance News Crawler — fetches stock-specific news via Yahoo's search API.

Free, no API key required. Returns headlines with publisher and timestamp.
Rate limit: be gentle (~1 req/sec).

Usage:
    from src.data_sources.yahoo_news import fetch_yahoo_news, get_yahoo_news_signal

    articles = fetch_yahoo_news("AAPL")
    signal = get_yahoo_news_signal("AAPL")
"""

import logging
import requests
from datetime import datetime

log = logging.getLogger(__name__)

_SESSION = None

def _get_session():
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
    return _SESSION


def fetch_yahoo_news(symbol: str, count: int = 20) -> list[dict]:
    """Fetch news articles for a stock from Yahoo Finance search API.

    Args:
        symbol: Stock ticker (e.g., "AAPL", "1155.KL")
        count: Max articles to return

    Returns:
        List of {title, publisher, url, published_at, source_platform}
    """
    try:
        session = _get_session()
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        params = {
            "q": symbol,
            "quotesCount": 0,
            "newsCount": count,
            "enableFuzzyQuery": False,
        }

        resp = session.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return []

        data = resp.json()
        articles = []

        for item in data.get("news", []):
            title = item.get("title", "").strip()
            if not title:
                continue

            # Convert Unix timestamp to ISO
            ts = item.get("providerPublishTime", 0)
            try:
                published = datetime.fromtimestamp(ts).isoformat() if ts else ""
            except (ValueError, OSError):
                published = ""

            articles.append({
                "headline": title,
                "summary": "",
                "url": item.get("link", ""),
                "source_name": item.get("publisher", "Yahoo Finance"),
                "source_platform": "yahoo-finance",
                "related_symbol": symbol,
                "fetched_at": datetime.now().isoformat(),
                "published_at": published,
            })

        return articles
    except Exception as e:
        log.warning(f"Yahoo Finance news failed for {symbol}: {e}")
        return []


def fetch_yahoo_market_news(count: int = 30) -> list[dict]:
    """Fetch general market news from Yahoo Finance.

    Searches for broad market terms to get top headlines.
    """
    all_articles = []
    seen_titles = set()

    for query in ["stock market", "S&P 500", "KLSE Bursa Malaysia"]:
        articles = fetch_yahoo_news(query, count=10)
        for a in articles:
            if a["headline"] not in seen_titles:
                seen_titles.add(a["headline"])
                a["related_symbol"] = ""  # market-wide, not stock-specific
                all_articles.append(a)

    return all_articles[:count]
