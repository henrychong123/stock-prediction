"""
Malaysia-specific news fetcher using free sources.

Since Finnhub doesn't cover Bursa Malaysia, we use:
1. Google News RSS (unlimited, no key) - broadest coverage
2. The Edge Markets RSS (no key) - Malaysia's #1 financial news
3. NewsAPI.org (100 req/day, key needed) - structured headlines

All feeds are parsed and run through sentiment analysis.
"""

import feedparser
import requests
from datetime import datetime, timedelta

from config.settings import (
    MY_STOCK_NAMES,
    MY_INFLUENTIAL_FIGURES,
    MY_GEOPOLITICAL_KEYWORDS,
)


# ===== GOOGLE NEWS RSS (unlimited, no key) =====

GOOGLE_NEWS_FEEDS = {
    "bursa_general": (
        "https://news.google.com/rss/search?"
        "q=Bursa+Malaysia+stock+market&hl=en-MY&gl=MY&ceid=MY:en"
    ),
    "klse": (
        "https://news.google.com/rss/search?"
        "q=KLSE+OR+%22Bursa+Malaysia%22&hl=en-MY&gl=MY&ceid=MY:en"
    ),
    "my_economy": (
        "https://news.google.com/rss/search?"
        "q=Malaysia+economy+ringgit+bank+negara&hl=en-MY&gl=MY&ceid=MY:en"
    ),
    "palm_oil": (
        "https://news.google.com/rss/search?"
        "q=%22palm+oil%22+Malaysia+price&hl=en-MY&gl=MY&ceid=MY:en"
    ),
}


def fetch_google_news_my(max_per_feed: int = 10) -> list[dict]:
    """Fetch Malaysian financial news from Google News RSS.

    Free, unlimited, no API key needed.

    Returns:
        List of article dicts with headline, source, datetime, sentiment
    """
    from src.data_sources.news_sentiment import analyze_sentiment

    articles = []
    seen_titles = set()

    for feed_name, url in GOOGLE_NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                title = entry.get("title", "")
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                # Google News title format: "Headline - Source"
                parts = title.rsplit(" - ", 1)
                headline = parts[0]
                source = parts[1] if len(parts) > 1 else "Google News"

                # Parse date
                published = entry.get("published", "")
                try:
                    dt = datetime(*entry.published_parsed[:6]).isoformat()
                except Exception:
                    dt = published

                sentiment = analyze_sentiment(headline)

                articles.append({
                    "headline": headline,
                    "summary": entry.get("summary", "")[:200],
                    "source": source,
                    "url": entry.get("link", ""),
                    "datetime": dt,
                    "sentiment": sentiment,
                    "platform": "google-news-my",
                    "feed": feed_name,
                })
        except Exception:
            continue

    # Sort by date (most recent first)
    articles.sort(key=lambda a: a.get("datetime", ""), reverse=True)
    return articles


# ===== THE EDGE MARKETS RSS (free, no key) =====

EDGE_RSS_FEEDS = {
    "markets": "https://www.theedgemarkets.com/rss",
}


def fetch_edge_markets_news(max_articles: int = 15) -> list[dict]:
    """Fetch news from The Edge Markets (Malaysia's top financial news).

    Free, no API key needed. Covers Bursa Malaysia extensively.

    Returns:
        List of article dicts
    """
    from src.data_sources.news_sentiment import analyze_sentiment

    articles = []

    for feed_name, url in EDGE_RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_articles]:
                title = entry.get("title", "")
                if not title:
                    continue

                try:
                    dt = datetime(*entry.published_parsed[:6]).isoformat()
                except Exception:
                    dt = entry.get("published", "")

                summary = entry.get("summary", "")[:200]
                text_for_sentiment = f"{title}. {summary}" if summary else title
                sentiment = analyze_sentiment(text_for_sentiment)

                articles.append({
                    "headline": title,
                    "summary": summary,
                    "source": "The Edge Markets",
                    "url": entry.get("link", ""),
                    "datetime": dt,
                    "sentiment": sentiment,
                    "platform": "theedge-my",
                })
        except Exception:
            continue

    return articles


# ===== NEWSAPI.ORG (100 req/day, key needed) =====

def fetch_newsapi_my(api_key: str = "", max_articles: int = 15) -> list[dict]:
    """Fetch Malaysian business headlines from NewsAPI.org.

    Requires API key (free at newsapi.org). 100 requests/day limit.
    Covers: The Star, Malay Mail, The Edge, and more.

    Args:
        api_key: NewsAPI key. If empty, tries NEWSAPI_KEY env var.
        max_articles: Max articles to return

    Returns:
        List of article dicts
    """
    import os
    from src.data_sources.news_sentiment import analyze_sentiment

    if not api_key:
        api_key = os.getenv("NEWSAPI_KEY", "")
    if not api_key:
        return []  # Silently skip if no key (optional source)

    articles = []
    try:
        # Top headlines for Malaysia business
        resp = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={
                "country": "my",
                "category": "business",
                "pageSize": max_articles,
                "apiKey": api_key,
            },
            timeout=10,
        )
        data = resp.json()

        for item in data.get("articles", []):
            title = item.get("title", "")
            if not title:
                continue

            description = item.get("description", "") or ""
            text = f"{title}. {description}" if description else title
            sentiment = analyze_sentiment(text)

            articles.append({
                "headline": title,
                "summary": description[:200],
                "source": item.get("source", {}).get("name", "NewsAPI"),
                "url": item.get("url", ""),
                "datetime": item.get("publishedAt", ""),
                "sentiment": sentiment,
                "platform": "newsapi-my",
            })
    except Exception:
        pass

    return articles


# ===== COMBINED: ALL MALAYSIA NEWS =====

def fetch_all_my_news() -> list[dict]:
    """Fetch and combine news from all Malaysian sources.

    Uses (in order of reliability):
    1. Google News RSS (always works, unlimited)
    2. The Edge Markets RSS (always works, best quality)
    3. NewsAPI.org (if key available, 100 req/day)

    Returns:
        Combined and deduplicated list of articles, sorted by date
    """
    all_articles = []

    # Google News (primary - unlimited)
    all_articles.extend(fetch_google_news_my())

    # The Edge Markets (high quality Malaysian finance)
    all_articles.extend(fetch_edge_markets_news())

    # NewsAPI (optional, needs key)
    all_articles.extend(fetch_newsapi_my())

    # Deduplicate by headline similarity
    seen = set()
    unique = []
    for a in all_articles:
        # Normalize: lowercase, first 60 chars
        key = a["headline"].lower()[:60]
        if key not in seen:
            seen.add(key)
            unique.append(a)

    # Sort by date
    unique.sort(key=lambda a: a.get("datetime", ""), reverse=True)
    return unique


def fetch_my_influential_news() -> list[dict]:
    """Fetch news mentioning Malaysian influential figures/institutions.

    Searches Google News RSS for mentions of Anwar Ibrahim, Robert Kuok,
    Bank Negara Malaysia, Petronas, etc.

    Returns:
        List of articles related to influential Malaysian figures
    """
    from src.data_sources.news_sentiment import analyze_sentiment

    figure_news = []
    seen = set()

    for figure in MY_INFLUENTIAL_FIGURES:
        query = figure.replace(" ", "+")
        url = (
            f"https://news.google.com/rss/search?"
            f"q={query}+Malaysia&hl=en-MY&gl=MY&ceid=MY:en"
        )

        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "")
                if not title or title in seen:
                    continue
                seen.add(title)

                parts = title.rsplit(" - ", 1)
                headline = parts[0]
                source = parts[1] if len(parts) > 1 else "Google News"

                try:
                    dt = datetime(*entry.published_parsed[:6]).isoformat()
                except Exception:
                    dt = ""

                sentiment = analyze_sentiment(headline)

                figure_news.append({
                    "figure": figure,
                    "headline": headline,
                    "source": source,
                    "datetime": dt,
                    "sentiment": sentiment,
                    "platform": "google-news-my",
                })
        except Exception:
            continue

    return figure_news


def get_my_news_signal(symbol: str = "") -> dict:
    """Aggregate Malaysian news sentiment into a trading signal.

    If a symbol is provided, filters for relevant news.
    Otherwise returns overall market sentiment.

    Returns:
        Dict with signal, strength, article_count, reasons
    """
    articles = fetch_all_my_news()

    if not articles:
        return {
            "signal": "neutral",
            "strength": 0.5,
            "article_count": 0,
            "reasons": ["No Malaysian news data available"],
        }

    # If symbol provided, filter for relevant articles
    if symbol:
        stock_name = MY_STOCK_NAMES.get(symbol, "")
        code = symbol.replace(".KL", "")
        keywords = [code.lower()]
        if stock_name:
            keywords.extend(stock_name.lower().split())

        relevant = [
            a for a in articles
            if any(kw in a["headline"].lower() for kw in keywords)
        ]
        # Fall back to all articles if none match
        if relevant:
            articles = relevant

    scores = [a["sentiment"]["score"] for a in articles]
    avg_score = sum(scores) / len(scores)
    strength = (avg_score + 1) / 2  # Normalize to 0-1

    if avg_score > 0.1:
        signal = "bullish"
    elif avg_score < -0.1:
        signal = "bearish"
    else:
        signal = "neutral"

    sorted_articles = sorted(articles, key=lambda x: abs(x["sentiment"]["score"]), reverse=True)
    top_headlines = [a["headline"] for a in sorted_articles[:5]]

    return {
        "signal": signal,
        "strength": round(strength, 3),
        "avg_sentiment": round(avg_score, 3),
        "article_count": len(articles),
        "reasons": top_headlines,
    }
