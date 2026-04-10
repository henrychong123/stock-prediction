"""
Historical News Sentiment Collector — backfills daily_features with news sentiment
for all US stocks using Finnhub company_news() + FinBERT.

This is the collector that fills the 8 dead sentiment features in training data.

Data source: Finnhub company_news() → FinBERT sentiment analysis
Rate limit: 60 req/min free tier

Usage:
    python src/data/collect_news_history.py                  # all core stocks, 12 months
    python src/data/collect_news_history.py --symbol AAPL    # specific stock
    python src/data/collect_news_history.py --months 6       # last 6 months only
    python src/data/collect_news_history.py --skip-finbert   # save headlines only (fast)
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import finnhub
from config.settings import FINNHUB_API_KEY
from src.database import init_db, save_daily_features, get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# FinBERT model (lazy loaded)
_finbert_pipeline = None


def _get_finbert():
    """Lazy-load FinBERT pipeline."""
    global _finbert_pipeline
    if _finbert_pipeline is not None:
        return _finbert_pipeline

    try:
        from transformers import pipeline
        log.info("Loading FinBERT model (first time may take ~30s)...")
        _finbert_pipeline = pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            device=-1,  # CPU
            truncation=True,
            max_length=512,
        )
        log.info("FinBERT loaded.")
        return _finbert_pipeline
    except Exception as e:
        log.warning(f"FinBERT not available: {e}")
        return None


def _analyze_sentiment_batch(headlines: list[str]) -> list[float]:
    """Run FinBERT on a batch of headlines. Returns list of scores (-1 to +1)."""
    pipe = _get_finbert()
    if not pipe or not headlines:
        return [0.0] * len(headlines)

    try:
        results = pipe(headlines, batch_size=32)
        scores = []
        for r in results:
            label = r["label"].lower()
            score = r["score"]
            if label == "positive":
                scores.append(score)
            elif label == "negative":
                scores.append(-score)
            else:
                scores.append(0.0)
        return scores
    except Exception:
        return [0.0] * len(headlines)


def _fetch_company_news(symbol: str, from_date: str, to_date: str) -> list[dict]:
    """Fetch company news from Finnhub for a date range."""
    if not FINNHUB_API_KEY:
        return []

    try:
        client = finnhub.Client(api_key=FINNHUB_API_KEY)
        articles = client.company_news(symbol, _from=from_date, to=to_date)
        return articles or []
    except Exception:
        return []


def _get_existing_dates(symbol: str) -> set:
    """Get dates that already have daily_features for this symbol."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT date FROM daily_features WHERE symbol = ?", (symbol,)
        ).fetchall()
        conn.close()
        return {r["date"] for r in rows}
    except Exception:
        return set()


def collect_stock_news(symbol: str, months_back: int = 12, skip_finbert: bool = False):
    """Collect and analyze news for one stock, saving daily aggregated sentiment."""
    existing = _get_existing_dates(symbol)

    end = datetime.now()
    start = end - timedelta(days=months_back * 30)

    # Process in monthly chunks (Finnhub returns max ~500 per request)
    total_articles = 0
    total_days = 0
    current = start

    while current < end:
        chunk_end = min(current + timedelta(days=30), end)
        from_str = current.strftime("%Y-%m-%d")
        to_str = chunk_end.strftime("%Y-%m-%d")

        articles = _fetch_company_news(symbol, from_str, to_str)
        time.sleep(1.1)  # rate limit

        if not articles:
            current = chunk_end
            continue

        # Group articles by date
        by_date = defaultdict(list)
        for article in articles:
            ts = article.get("datetime", 0)
            if ts:
                date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                headline = article.get("headline", "")
                if headline:
                    by_date[date_str].append(headline)

        # Analyze sentiment per day
        for date_str, headlines in by_date.items():
            if date_str in existing:
                continue  # skip already-collected dates

            if skip_finbert:
                avg_sentiment = 0.0
            else:
                scores = _analyze_sentiment_batch(headlines[:20])  # cap at 20 per day
                avg_sentiment = sum(scores) / len(scores) if scores else 0.0

            row = {
                "symbol": symbol,
                "date": date_str,
                "news_sentiment": round(avg_sentiment, 4),
                "news_count": len(headlines),
                "news_top_headline": headlines[0][:200] if headlines else "",
                "reddit_sentiment": None,
                "reddit_count": 0,
                "figure_sentiment": None,
                "figure_count": 0,
                "figure_top": "",
                "gdelt_tone": None,
                "fear_greed": None,
            }
            save_daily_features(row)
            total_days += 1

        total_articles += len(articles)
        current = chunk_end

    return total_articles, total_days


def run(symbol: str = None, months: int = 12, skip_finbert: bool = False):
    init_db()

    if symbol:
        symbols = [symbol]
    else:
        # Core stocks: Bursa + top US
        try:
            from config.stock_universe import get_core_stocks
            symbols = [s["symbol"] for s in get_core_stocks()]
        except ImportError:
            symbols = ["TSLA", "AAPL", "NVDA", "GOOGL", "AMZN", "MSFT", "META"]

    # Filter to US stocks only (Finnhub company_news is US-focused)
    us_symbols = [s for s in symbols if not s.endswith(".KL") and not s.startswith("^")]

    total = len(us_symbols)
    log.info(f"Collecting {months}-month news history for {total} US stocks...")
    if skip_finbert:
        log.info("  FinBERT disabled — saving article counts only")

    ok = 0
    grand_articles = 0
    grand_days = 0

    for i, sym in enumerate(us_symbols, 1):
        log.info(f"Processing {i}/{total}: {sym}")

        articles, days = collect_stock_news(sym, months_back=months, skip_finbert=skip_finbert)
        if days > 0:
            ok += 1
            grand_articles += articles
            grand_days += days
            log.info(f"  {sym}: {articles} articles → {days} daily records")
        else:
            log.info(f"  {sym}: no new data")

        if i % 20 == 0:
            log.info(f"  Progress: {i}/{total} ({ok} with data, {grand_days} daily records)")

    log.info(f"\nDone — {ok}/{total} stocks, {grand_articles} articles → {grand_days} daily sentiment records")


if __name__ == "__main__":
    args = sys.argv[1:]
    sym = None
    months = 12
    skip_fb = "--skip-finbert" in args

    for i, a in enumerate(args):
        if a == "--symbol" and i + 1 < len(args):
            sym = args[i + 1]
        elif a == "--months" and i + 1 < len(args):
            months = int(args[i + 1])

    run(symbol=sym, months=months, skip_finbert=skip_fb)
