"""
News sentiment analysis using Finnhub for news fetching and FinBERT for sentiment.

Data sources:
- Finnhub: Market news and company-specific news (free: 60 req/min)
- FinBERT: Financial domain BERT model for accurate sentiment scoring

Falls back to keyword-based sentiment if FinBERT model is not downloaded.
"""

import finnhub
import pandas as pd
from datetime import datetime, timedelta

from config.settings import FINNHUB_API_KEY, SENTIMENT_MODEL, INFLUENTIAL_FIGURES


# Lazy-load the sentiment model (heavy import)
_sentiment_pipeline = None


def _get_sentiment_pipeline():
    """Lazy-load FinBERT sentiment pipeline."""
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        try:
            from transformers import pipeline
            _sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=SENTIMENT_MODEL,
                top_k=None,
            )
        except Exception:
            _sentiment_pipeline = "unavailable"
    return _sentiment_pipeline


def _keyword_sentiment(text: str) -> dict:
    """Fallback keyword-based sentiment when FinBERT is unavailable."""
    text_lower = text.lower()

    positive_words = [
        "surge", "rally", "gain", "profit", "growth", "bullish", "upgrade",
        "beat", "record", "boom", "soar", "jump", "rise", "strong", "positive",
        "outperform", "buy", "opportunity", "recovery", "optimistic",
    ]
    negative_words = [
        "crash", "plunge", "loss", "decline", "bearish", "downgrade", "miss",
        "recession", "fall", "drop", "weak", "negative", "sell", "risk",
        "warning", "fear", "crisis", "war", "sanctions", "tariff",
    ]

    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)
    total = pos_count + neg_count

    if total == 0:
        return {"label": "neutral", "score": 0.0}

    net = (pos_count - neg_count) / total
    if net > 0.2:
        return {"label": "positive", "score": round(net, 3)}
    elif net < -0.2:
        return {"label": "negative", "score": round(net, 3)}
    return {"label": "neutral", "score": round(net, 3)}


def analyze_sentiment(text: str) -> dict:
    """Analyze sentiment of a text using FinBERT or keyword fallback.

    Returns:
        Dict with label (positive/negative/neutral) and score (-1 to 1)
    """
    pipe = _get_sentiment_pipeline()

    if pipe == "unavailable":
        return _keyword_sentiment(text)

    results = pipe(text[:512])  # FinBERT max input length
    if not results:
        return {"label": "neutral", "score": 0.0}

    # FinBERT returns list of dicts with label and score
    scores = {r["label"]: r["score"] for r in results[0]}
    pos = scores.get("positive", 0)
    neg = scores.get("negative", 0)
    net_score = pos - neg

    if net_score > 0.1:
        label = "positive"
    elif net_score < -0.1:
        label = "negative"
    else:
        label = "neutral"

    return {"label": label, "score": round(net_score, 3)}


def fetch_market_news(category: str = "general") -> list[dict]:
    """Fetch latest market news from Finnhub.

    Args:
        category: "general", "forex", "crypto", or "merger"

    Returns:
        List of news articles with headline, summary, source, datetime, sentiment
    """
    if not FINNHUB_API_KEY:
        return [{"error": "FINNHUB_API_KEY not set. Get one free at https://finnhub.io/register"}]

    client = finnhub.Client(api_key=FINNHUB_API_KEY)
    news = client.general_news(category, min_id=0)

    articles = []
    for item in news[:20]:  # Limit to 20 most recent
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        text = f"{headline}. {summary}" if summary else headline

        sentiment = analyze_sentiment(text)

        articles.append({
            "headline": headline,
            "summary": summary[:200] if summary else "",
            "source": item.get("source", "unknown"),
            "url": item.get("url", ""),
            "datetime": datetime.fromtimestamp(item.get("datetime", 0)).isoformat(),
            "sentiment": sentiment,
        })

    return articles


def fetch_company_news(symbol: str, days_back: int = 7) -> list[dict]:
    """Fetch company-specific news from Finnhub.

    Args:
        symbol: Stock ticker
        days_back: How many days back to fetch

    Returns:
        List of company news articles with sentiment
    """
    if not FINNHUB_API_KEY:
        return [{"error": "FINNHUB_API_KEY not set"}]

    client = finnhub.Client(api_key=FINNHUB_API_KEY)
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    news = client.company_news(symbol, _from=start, to=end)

    articles = []
    for item in news[:15]:
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        text = f"{headline}. {summary}" if summary else headline

        sentiment = analyze_sentiment(text)

        articles.append({
            "headline": headline,
            "source": item.get("source", "unknown"),
            "datetime": datetime.fromtimestamp(item.get("datetime", 0)).isoformat(),
            "sentiment": sentiment,
        })

    return articles


def fetch_influential_figure_news() -> list[dict]:
    """Fetch news about influential figures (Musk, Trump, etc.).

    Since X/Twitter free API is effectively dead, we monitor news coverage
    of influential people's statements and posts instead.

    Returns:
        List of news items about influential figures with sentiment
    """
    if not FINNHUB_API_KEY:
        return [{"error": "FINNHUB_API_KEY not set"}]

    client = finnhub.Client(api_key=FINNHUB_API_KEY)
    news = client.general_news("general", min_id=0)

    figure_news = []
    for item in news:
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        text = f"{headline} {summary}".lower()

        for figure in INFLUENTIAL_FIGURES:
            if figure.lower() in text:
                full_text = f"{headline}. {summary}" if summary else headline
                sentiment = analyze_sentiment(full_text)

                figure_news.append({
                    "figure": figure,
                    "headline": headline,
                    "source": item.get("source", "unknown"),
                    "datetime": datetime.fromtimestamp(item.get("datetime", 0)).isoformat(),
                    "sentiment": sentiment,
                })
                break  # Don't double-count if multiple figures mentioned

    return figure_news


def get_news_signal(symbol: str) -> dict:
    """Aggregate news sentiment into a trading signal.

    Returns:
        Dict with signal (bullish/bearish/neutral), strength, and summary
    """
    company_news = fetch_company_news(symbol)
    if not company_news or "error" in company_news[0]:
        return {"signal": "neutral", "strength": 0.5, "article_count": 0, "reasons": ["No news data available"]}

    scores = [a["sentiment"]["score"] for a in company_news]
    if not scores:
        return {"signal": "neutral", "strength": 0.5, "article_count": 0, "reasons": ["No articles found"]}

    avg_score = sum(scores) / len(scores)
    strength = (avg_score + 1) / 2  # Normalize to 0-1

    if avg_score > 0.1:
        signal = "bullish"
    elif avg_score < -0.1:
        signal = "bearish"
    else:
        signal = "neutral"

    # Get top headlines
    sorted_news = sorted(company_news, key=lambda x: abs(x["sentiment"]["score"]), reverse=True)
    top_headlines = [a["headline"] for a in sorted_news[:3]]

    return {
        "signal": signal,
        "strength": round(strength, 3),
        "avg_sentiment": round(avg_score, 3),
        "article_count": len(company_news),
        "reasons": top_headlines,
    }
