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

    try:
        client = finnhub.Client(api_key=FINNHUB_API_KEY)
        news = client.general_news(category, min_id=0)
    except Exception:
        return []

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

    try:
        client = finnhub.Client(api_key=FINNHUB_API_KEY)
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        news = client.company_news(symbol, _from=start, to=end)
    except Exception:
        return []

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


def fetch_influential_figure_news(figures: list[str] = None,
                                   include_my: bool = False) -> list[dict]:
    """Fetch news about influential figures via Google News RSS + Finnhub.

    Combines two sources:
    1. Google News RSS per figure (free, unlimited, real-time)
    2. Finnhub general news scan (existing, limited to ~20 articles)

    Returns:
        List of news items about influential figures with sentiment
    """
    import feedparser
    from config.settings import MY_INFLUENTIAL_FIGURES

    if figures is None:
        figures = list(INFLUENTIAL_FIGURES)
        if include_my:
            figures += MY_INFLUENTIAL_FIGURES

    figure_news = []
    seen_headlines = set()

    # ── Source 1: Google News RSS per figure (with timeout) ─────────────
    import urllib.request

    for figure in figures:
        query = figure.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={query}+stock+market&hl=en-US&gl=US&ceid=US:en"
        try:
            # Use urllib with timeout instead of feedparser's default (no timeout)
            req = urllib.request.urlopen(url, timeout=8)
            raw = req.read()
            feed = feedparser.parse(raw)
            for entry in feed.entries[:3]:  # top 3 per figure (was 5, reduced for speed)
                headline = entry.get("title", "")
                # Google News format: "Headline - Source"
                parts = headline.rsplit(" - ", 1)
                clean_headline = parts[0].strip()
                source = parts[1].strip() if len(parts) > 1 else "Google News"

                # Deduplicate
                norm = clean_headline[:60].lower()
                if norm in seen_headlines:
                    continue
                seen_headlines.add(norm)

                # Parse date
                pub = entry.get("published_parsed")
                dt = datetime(*pub[:6]).isoformat() if pub else datetime.now().isoformat()

                sentiment = analyze_sentiment(clean_headline)
                figure_news.append({
                    "figure": figure,
                    "headline": clean_headline,
                    "source": source,
                    "url": entry.get("link", ""),
                    "datetime": dt,
                    "sentiment": sentiment,
                    "platform": "google-news",
                })
        except Exception:
            continue

    # ── Source 2: Finnhub general news scan ────────────────────────────────
    if FINNHUB_API_KEY:
        try:
            client = finnhub.Client(api_key=FINNHUB_API_KEY)
            news = client.general_news("general", min_id=0)

            for item in news:
                headline = item.get("headline", "")
                summary = item.get("summary", "")
                text = f"{headline} {summary}".lower()

                for figure in figures:
                    if figure.lower() in text:
                        norm = headline[:60].lower()
                        if norm in seen_headlines:
                            break
                        seen_headlines.add(norm)

                        full_text = f"{headline}. {summary}" if summary else headline
                        sentiment = analyze_sentiment(full_text)
                        figure_news.append({
                            "figure": figure,
                            "headline": headline,
                            "source": item.get("source", "unknown"),
                            "url": item.get("url", ""),
                            "datetime": datetime.fromtimestamp(item.get("datetime", 0)).isoformat(),
                            "sentiment": sentiment,
                            "platform": "finnhub",
                        })
                        break
        except Exception:
            pass

    # Sort by datetime descending
    figure_news.sort(key=lambda x: x.get("datetime", ""), reverse=True)
    return figure_news


def get_figure_signal(symbol: str) -> dict:
    """Get influential figure activity relevant to a stock.

    Returns figure-level sentiment breakdown + overall signal.
    """
    from config.settings import (FIGURE_STOCK_MAP, MY_FIGURE_STOCK_MAP,
                                  MY_INFLUENTIAL_FIGURES)

    sym_upper = symbol.upper().replace(".KL", "")
    is_my = symbol.upper().endswith(".KL") or symbol.startswith("^KL")

    # Determine which figures are relevant to this stock
    stock_map = {**FIGURE_STOCK_MAP, **MY_FIGURE_STOCK_MAP} if is_my else FIGURE_STOCK_MAP
    relevant_figures = []
    for figure, stocks in stock_map.items():
        # Match exact symbol or base code
        for s in stocks:
            s_clean = s.upper().replace(".KL", "")
            if s_clean == sym_upper or s_clean == symbol.upper():
                relevant_figures.append(figure)
                break

    # If no specific mapping, use all figures for broad market stocks
    if not relevant_figures:
        if is_my:
            relevant_figures = list(MY_INFLUENTIAL_FIGURES)
        else:
            relevant_figures = list(INFLUENTIAL_FIGURES)

    # Fetch news for relevant figures
    all_news = fetch_influential_figure_news(figures=relevant_figures, include_my=is_my)

    if not all_news:
        return {
            "figures": [],
            "total_mentions": 0,
            "overall_sentiment": 0,
            "signal": "neutral",
        }

    # Group by figure
    by_figure = {}
    for item in all_news:
        fig = item["figure"]
        if fig not in by_figure:
            by_figure[fig] = {"articles": [], "scores": []}
        by_figure[fig]["articles"].append(item)
        by_figure[fig]["scores"].append(item["sentiment"]["score"])

    # Build figure summaries
    figures_out = []
    all_scores = []
    for fig, data in by_figure.items():
        avg = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
        all_scores.extend(data["scores"])

        label = "bullish" if avg > 0.1 else "bearish" if avg < -0.1 else "neutral"
        figures_out.append({
            "name": fig,
            "mention_count": len(data["articles"]),
            "avg_sentiment": round(avg, 3),
            "signal": label,
            "latest_headline": data["articles"][0]["headline"] if data["articles"] else "",
            "latest_source": data["articles"][0].get("source", "") if data["articles"] else "",
            "latest_datetime": data["articles"][0].get("datetime", "") if data["articles"] else "",
            "latest_url": data["articles"][0].get("url", "") if data["articles"] else "",
            "articles": data["articles"][:3],  # top 3 per figure
        })

    # Sort by mention count
    figures_out.sort(key=lambda x: x["mention_count"], reverse=True)

    overall = sum(all_scores) / len(all_scores) if all_scores else 0
    signal = "bullish" if overall > 0.1 else "bearish" if overall < -0.1 else "neutral"

    return {
        "figures": figures_out,
        "total_mentions": len(all_news),
        "overall_sentiment": round(overall, 3),
        "signal": signal,
    }


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
