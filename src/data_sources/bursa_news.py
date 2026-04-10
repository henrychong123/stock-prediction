"""
Bursa Malaysia News Crawlers — scrapes i3investor and KLSE Screener
for Malaysia-specific stock news, analyst reports, and company announcements.

Free, no API keys. Fills the gap where Finnhub has no Bursa coverage.

Sources:
1. i3investor.com — market buzz, stock-specific blogs, analyst reports
2. klsescreener.com — company news, announcements

Usage:
    from src.data_sources.bursa_news import fetch_i3investor_news, fetch_klse_screener_news
"""

import logging
import re
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
            "Accept-Language": "en-US,en;q=0.9",
        })
    return _SESSION


# ── i3investor ───────────────────────────────────────────────────────────────

def fetch_i3investor_market_buzz(max_articles: int = 20) -> list[dict]:
    """Fetch market buzz articles from i3investor (general Bursa news)."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("beautifulsoup4 not installed. Run: pip install beautifulsoup4")
        return []

    try:
        session = _get_session()
        resp = session.get("https://klse.i3investor.com/web/blog/market-buzz", timeout=15)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = []
        seen = set()

        for link in soup.select('a[href*="/web/blog/detail/"]'):
            title = link.get_text(strip=True)
            href = link.get("href", "")

            if not title or len(title) < 15 or title in seen:
                continue

            # Skip non-English or promotional content
            if any(skip in title.lower() for skip in ["moomoo", "win gold", "etf with"]):
                continue

            seen.add(title)
            articles.append({
                "headline": title,
                "summary": "",
                "url": f"https://klse.i3investor.com{href}" if href.startswith("/") else href,
                "source_name": "i3investor",
                "source_platform": "i3investor",
                "related_symbol": "",
                "fetched_at": datetime.now().isoformat(),
            })

            if len(articles) >= max_articles:
                break

        return articles
    except Exception as e:
        log.warning(f"i3investor market buzz failed: {e}")
        return []


def fetch_i3investor_stock(stock_code: str, max_articles: int = 10) -> list[dict]:
    """Fetch stock-specific news/blogs from i3investor.

    Args:
        stock_code: Bursa stock code WITHOUT .KL suffix (e.g., "1155" for Maybank)
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    try:
        session = _get_session()
        url = f"https://klse.i3investor.com/web/stock/overview/{stock_code}"
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = []
        seen = set()

        symbol = f"{stock_code}.KL"

        for link in soup.select('a[href*="blog/detail"], a[href*="announcement"]'):
            title = link.get_text(strip=True)
            href = link.get("href", "")

            if not title or len(title) < 10 or title in seen:
                continue
            if title.lower() in ("announcement", "blog", "news"):
                continue

            seen.add(title)
            articles.append({
                "headline": title,
                "summary": "",
                "url": f"https://klse.i3investor.com{href}" if href.startswith("/") else href,
                "source_name": "i3investor",
                "source_platform": "i3investor",
                "related_symbol": symbol,
                "fetched_at": datetime.now().isoformat(),
            })

            if len(articles) >= max_articles:
                break

        return articles
    except Exception as e:
        log.warning(f"i3investor stock {stock_code} failed: {e}")
        return []


# ── KLSE Screener ────────────────────────────────────────────────────────────

def fetch_klse_screener_news(max_articles: int = 30) -> list[dict]:
    """Fetch latest news from KLSE Screener."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    try:
        session = _get_session()
        resp = session.get("https://www.klsescreener.com/v2/news", timeout=15)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = []
        seen = set()

        for link in soup.select("a"):
            href = link.get("href", "")
            title = link.get_text(strip=True)

            if "/v2/news" not in href or not title or len(title) < 15:
                continue
            if title in seen:
                continue

            # Skip non-English articles (simple heuristic)
            ascii_ratio = sum(1 for c in title if ord(c) < 128) / len(title)
            if ascii_ratio < 0.7:
                continue

            seen.add(title)
            articles.append({
                "headline": title,
                "summary": "",
                "url": f"https://www.klsescreener.com{href}" if href.startswith("/") else href,
                "source_name": "KLSE Screener",
                "source_platform": "klse-screener",
                "related_symbol": "",
                "fetched_at": datetime.now().isoformat(),
            })

            if len(articles) >= max_articles:
                break

        return articles
    except Exception as e:
        log.warning(f"KLSE Screener failed: {e}")
        return []


# ── Combined ─────────────────────────────────────────────────────────────────

def fetch_all_bursa_news(stock_codes: list[str] = None) -> list[dict]:
    """Fetch news from all Bursa-specific sources.

    Args:
        stock_codes: Optional list of Bursa codes (e.g., ["1155", "5183"]).
                     If None, fetches market-wide news only.
    """
    all_articles = []
    seen_titles = set()

    def _add(articles):
        for a in articles:
            key = a["headline"].lower()[:50]
            if key not in seen_titles:
                seen_titles.add(key)
                all_articles.append(a)

    # Market-wide
    log.info("  Fetching i3investor market buzz...")
    _add(fetch_i3investor_market_buzz())

    log.info("  Fetching KLSE Screener news...")
    _add(fetch_klse_screener_news())

    # Stock-specific
    if stock_codes:
        for code in stock_codes[:20]:  # limit to avoid too many requests
            articles = fetch_i3investor_stock(code)
            if articles:
                _add(articles)
                log.info(f"  i3investor {code}.KL: {len(articles)} articles")

    log.info(f"  Total Bursa news: {len(all_articles)} articles")
    return all_articles
