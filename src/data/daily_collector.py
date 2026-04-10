"""
Daily Feature Collector — collects sentiment and macro data that isn't
available historically. Run daily after market close.

Collects per stock:
- News sentiment (avg score, article count, top headline)
- Reddit sentiment (avg score, post count)
- Influential figure activity (mention count, avg sentiment)
- GDELT geopolitical tone
- Fear & Greed index value

Usage:
    python src/data/daily_collector.py              # collect all stocks
    python src/data/daily_collector.py AAPL TSLA    # specific stocks
    python src/data/daily_collector.py --my-only     # only Bursa stocks
"""

import sys
import os
import logging
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import init_db, save_daily_features
from config.settings import BURSA_INDUSTRIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

US_STOCKS = ["TSLA", "AAPL", "NVDA", "GOOGL", "AMZN", "MSFT", "META", "SPY", "QQQ", "DIA"]

def get_bursa_symbols() -> list[str]:
    symbols = []
    for ind in BURSA_INDUSTRIES.values():
        for s in ind["stocks"]:
            symbols.append(s["symbol"])
    return symbols


def _collect_news_sentiment(symbol: str) -> dict:
    """Get news sentiment for a stock."""
    try:
        from src.data_sources.news_sentiment import get_news_signal
        sig = get_news_signal(symbol)
        top = sig.get("reasons", [""])[0] if sig.get("reasons") else ""
        return {
            "news_sentiment": sig.get("avg_sentiment", 0),
            "news_count": sig.get("article_count", 0),
            "news_top_headline": top[:200],
        }
    except Exception as e:
        log.warning(f"  News sentiment failed for {symbol}: {e}")
        return {"news_sentiment": None, "news_count": 0, "news_top_headline": ""}


def _collect_reddit_sentiment(symbol: str) -> dict:
    """Get Reddit sentiment for a stock."""
    try:
        from src.data_sources.social_media import get_social_signal
        sig = get_social_signal(symbol)
        return {
            "reddit_sentiment": sig.get("avg_sentiment", 0),
            "reddit_count": sig.get("post_count", 0),
        }
    except Exception as e:
        log.warning(f"  Reddit sentiment failed for {symbol}: {e}")
        return {"reddit_sentiment": None, "reddit_count": 0}


def _collect_figure_sentiment(symbol: str) -> dict:
    """Get influential figure activity for a stock."""
    try:
        from src.data_sources.news_sentiment import get_figure_signal
        sig = get_figure_signal(symbol)
        top_fig = sig["figures"][0]["name"] if sig.get("figures") else ""
        return {
            "figure_sentiment": sig.get("overall_sentiment", 0),
            "figure_count": sig.get("total_mentions", 0),
            "figure_top": top_fig,
        }
    except Exception as e:
        log.warning(f"  Figure sentiment failed for {symbol}: {e}")
        return {"figure_sentiment": None, "figure_count": 0, "figure_top": ""}


def _collect_gdelt_tone() -> float:
    """Get GDELT geopolitical average tone (from stored data)."""
    try:
        from src.data_sources.geopolitical import get_geopolitical_signal
        sig = get_geopolitical_signal()
        return sig.get("avg_tone", 0)
    except Exception:
        return None


def _update_gdelt_history():
    """Fetch yesterday's GDELT tone data per industry and save to gdelt_history.
    This keeps the stored data fresh for the geopolitical signal."""
    try:
        from datetime import timedelta
        from src.data.collect_gdelt_history import fetch_gdelt_tone
        from config.industries import GDELT_KEYWORDS as INDUSTRY_KEYWORDS
        from src.database import save_gdelt_history_batch
        import time

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")

        log.info(f"Updating GDELT history for {yesterday}...")
        batch = []
        for industry, keywords in INDUSTRY_KEYWORDS.items():
            for kw in keywords:
                records = fetch_gdelt_tone(kw, yesterday, today)
                for rec in records:
                    d = rec.get("date", "")[:10]
                    if d == yesterday:
                        batch.append({
                            "date": d,
                            "industry": industry,
                            "avg_tone": round(rec.get("tone", 0), 4),
                            "article_count": rec.get("count", 1),
                            "keywords": kw,
                        })
                time.sleep(5)  # respect GDELT rate limits

        if batch:
            save_gdelt_history_batch(batch)
            log.info(f"  Saved {len(batch)} GDELT records for {yesterday}")
        else:
            log.info(f"  No GDELT data for {yesterday}")
    except Exception as e:
        log.warning(f"  GDELT history update failed: {e}")


def _collect_fear_greed() -> float:
    """Get Fear & Greed index value."""
    try:
        from src.analysis.market_indicators import calculate_fear_greed
        fg = calculate_fear_greed()
        return fg.get("score", 50)
    except Exception:
        return None


def run(symbols: list[str] = None, my_only=False, us_only=False, full=False):
    init_db()
    today = datetime.now().strftime("%Y-%m-%d")

    # Determine stocks — tiered strategy
    if symbols:
        stock_list = symbols
        sentiment_stocks = set(symbols)
    elif full:
        # Full universe for prices, core for sentiment
        try:
            from config.stock_universe import get_all_stocks, get_core_stocks
            stock_list = [s["symbol"] for s in get_all_stocks()]
            sentiment_stocks = set(s["symbol"] for s in get_core_stocks())
        except ImportError:
            stock_list = get_bursa_symbols() + US_STOCKS
            sentiment_stocks = set(stock_list)
    else:
        stock_list = []
        if not us_only:
            stock_list += get_bursa_symbols()
        if not my_only:
            stock_list += US_STOCKS
        sentiment_stocks = set(stock_list)  # all core stocks get sentiment

    total = len(stock_list)
    sentiment_count = len(sentiment_stocks)
    log.info(f"Collecting daily features for {total} stocks (date={today})")
    log.info(f"  Sentiment collection: {sentiment_count} stocks (core tier)")

    # Update GDELT history for yesterday (keeps stored data fresh)
    _update_gdelt_history()

    # Collect macro indicators once (shared across all stocks)
    log.info("Collecting macro indicators...")
    gdelt_tone = _collect_gdelt_tone()
    fear_greed = _collect_fear_greed()
    log.info(f"  GDELT tone: {gdelt_tone}, Fear & Greed: {fear_greed}")

    ok = 0
    for i, symbol in enumerate(stock_list, 1):
        is_core = symbol in sentiment_stocks

        if is_core:
            log.info(f"Processing {i}/{total}: {symbol} (core — with sentiment)")
        else:
            log.info(f"Processing {i}/{total}: {symbol} (prices only)")

        row = {
            "symbol": symbol,
            "date": today,
            "gdelt_tone": gdelt_tone,
            "fear_greed": fear_greed,
        }

        # Sentiment collection — only for core tier stocks
        if is_core:
            news = _collect_news_sentiment(symbol)
            row.update(news)

            # Reddit — only for US stocks with active subreddits
            if not symbol.endswith(".KL"):
                reddit = _collect_reddit_sentiment(symbol)
                row.update(reddit)
            else:
                row["reddit_sentiment"] = None
                row["reddit_count"] = 0

            figure = _collect_figure_sentiment(symbol)
            row.update(figure)
        else:
            # Non-core: only macro features (gdelt_tone, fear_greed)
            row["news_sentiment"] = None
            row["news_count"] = 0
            row["news_top_headline"] = ""
            row["reddit_sentiment"] = None
            row["reddit_count"] = 0
            row["figure_sentiment"] = None
            row["figure_count"] = 0
            row["figure_top"] = ""

        save_daily_features(row)
        ok += 1

        # Rate limit friendliness
        if i % 5 == 0:
            import time
            time.sleep(2)

    log.info(f"\nDone — {ok}/{total} stocks collected for {today}")


if __name__ == "__main__":
    args = sys.argv[1:]
    us_only = "--us-only" in args
    my_only = "--my-only" in args
    full = "--full" in args  # full universe (S&P 500 + Bursa)
    symbols = [a for a in args if not a.startswith("--")]
    run(symbols=symbols or None, my_only=my_only, us_only=us_only, full=full)
